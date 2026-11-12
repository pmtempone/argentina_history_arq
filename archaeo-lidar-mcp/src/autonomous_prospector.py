"""Scanner y Orquestador Autónomo de Prospección Arqueológica (Zero Human-in-the-Loop)."""

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import httpx
import numpy as np
import rasterio
from pyproj import CRS, Transformer
from rasterio.windows import from_bounds
from scipy.spatial import cKDTree
from shapely.geometry import shape

from src.config import settings
from src.core.anomaly_detector import detect_anomalies
from src.core.data_fetcher import TARGET_ZONES, fetch_elevation_tile
from src.core.highres_hunter import HighResLidarHunter
from src.core.literature_checker import check_academic_papers
from src.core.looting_monitor import evaluate_looting_alert
from src.core.ml_calibrator import load_calibrator, score_candidate
from src.core.relief_models import compute_slrm, compute_slope
from src.core.report_generator import generate_inapl_dossier
from src.core.spatial_validator import validate_anomaly_async
from src.core.visual_inspector import render_candidate_composite
from src.core.vlm_judge import DISCARD_VERDICTS, evaluate_candidate_with_vlm


def generate_sliding_windows_metric(
    bounds: Tuple[float, float, float, float],
    window_size_m: float = 500.0,
    overlap_ratio: float = 0.15,
) -> List[Tuple[int, int, float, float, float, float]]:
    """Genera la grilla de ventanas deslizantes métricas (ej. 500x500 m con 15% de overlap).

    Args:
        bounds: Tupla `(minx, miny, maxx, maxy)` en metros POSGAR 2007.
        window_size_m: Lado de cada celda cuadrada en metros (por defecto 500.0 m).
        overlap_ratio: Fracción de solapamiento entre celdas vecinas (por defecto 0.15).

    Returns:
        Lista de tuplas `(row_idx, col_idx, wx_min, wy_min, wx_max, wy_max)`.
    """
    minx, miny, maxx, maxy = bounds
    step_m = window_size_m * (1.0 - overlap_ratio)
    if step_m <= 0.0:
        raise ValueError("overlap_ratio debe ser menor a 1.0")

    xs = np.arange(minx, maxx, step_m)
    ys = np.arange(miny, maxy, step_m)

    min_cell_span = min(15.0, window_size_m * 0.3)
    windows: List[Tuple[int, int, float, float, float, float]] = []
    for r_idx, y0 in enumerate(ys):
        wy_min = float(y0)
        wy_max = float(min(y0 + window_size_m, maxy))
        if (wy_max - wy_min) < min_cell_span and r_idx > 0:
            continue
        for c_idx, x0 in enumerate(xs):
            wx_min = float(x0)
            wx_max = float(min(x0 + window_size_m, maxx))
            if (wx_max - wx_min) < min_cell_span and c_idx > 0:
                continue
            windows.append((r_idx, c_idx, wx_min, wy_min, wx_max, wy_max))

    return windows


def _extract_subtile_geotiff(
    src_dtm_path: Path,
    bbox_metric: Tuple[float, float, float, float],
    out_tile_path: Path,
) -> bool:
    """Extrae un sub-raster métrico para una celda de 500x500 m. Retorna False si está vacío."""
    wx_min, wy_min, wx_max, wy_max = bbox_metric
    out_tile_path.parent.mkdir(parents=True, exist_ok=True)

    with rasterio.open(src_dtm_path) as src:
        win = from_bounds(wx_min, wy_min, wx_max, wy_max, transform=src.transform)
        win = win.round_offsets().round_lengths()
        if win.width < 16 or win.height < 16:
            return False

        data = src.read(1, window=win, boundless=True, fill_value=-9999.0).astype(np.float32)
        valid = (data > -9000.0) & (~np.isnan(data))
        if np.sum(valid) < 50:
            return False

        win_transform = rasterio.windows.transform(win, src.transform)
        profile = src.profile.copy()
        profile.update(
            {
                "height": int(data.shape[0]),
                "width": int(data.shape[1]),
                "transform": win_transform,
                "dtype": "float32",
                "count": 1,
                "nodata": -9999.0,
            }
        )
        with rasterio.open(out_tile_path, "w", **profile) as dst:
            dst.write(data, 1)

    return True


def _deduplicate_candidates_metric(
    candidates: List[Dict[str, Any]],
    crs_epsg: int,
    min_separation_m: float = 30.0,
) -> List[Dict[str, Any]]:
    """Elimina candidatos duplicados en los bordes de solapamiento (15% overlap) usando cKDTree."""
    if len(candidates) <= 1:
        return candidates

    # Ordenar de mayor a menor score compuesto (confianza * |desviación SLRM|)
    sorted_cands = sorted(
        candidates,
        key=lambda f: float(f["properties"]["confidence"]) * abs(float(f["properties"]["mean_elevation_m"])),
        reverse=True,
    )

    to_metric = Transformer.from_crs(CRS.from_epsg(4326), CRS.from_epsg(crs_epsg), always_xy=True)
    coords_metric: List[Tuple[float, float]] = []
    for feat in sorted_cands:
        lon, lat = feat["properties"]["centroid_wgs84"]
        mx, my = to_metric.transform(float(lon), float(lat))
        coords_metric.append((float(mx), float(my)))

    pts = np.array(coords_metric, dtype=np.float64)
    tree = cKDTree(pts)

    kept_indices: List[int] = []
    suppressed = set()
    for i in range(len(sorted_cands)):
        if i in suppressed:
            continue
        kept_indices.append(i)
        neighbors = tree.query_ball_point(pts[i], r=min_separation_m)
        for n_idx in neighbors:
            if n_idx != i:
                suppressed.add(n_idx)

    return [sorted_cands[i] for i in kept_indices]


async def run_autonomous_prospector(
    target_zone: str = "ZONA_1_TASTIL",
    window_size_m: float = 500.0,
    overlap_ratio: float = 0.15,
    min_confidence: float = 0.70,
    min_elevation_m: float = 0.20,
    max_candidates_to_validate: int = 12,
    ml_mode: str = "advisory",
    cache_dir: Optional[Union[str, Path]] = None,
    processed_dir: Optional[Union[str, Path]] = None,
    reports_dir: Optional[Union[str, Path]] = None,
    http_client: Optional[httpx.AsyncClient] = None,
    hunt_highres: bool = False,
    highres_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Ejecuta de punta a punta la prospección autónoma sobre una zona objetivo del NOA o un dataset LiDAR/UAV de alta resolución.

    1. Si `hunt_highres=True`, busca y descarga autónomamente el mejor dataset LiDAR/UAV (0.15 m a 2.0 m) preservando su resolución nativa sub-métrica en POSGAR 2007; de lo contrario descarga el tile de `fetch_elevation_tile`.
    2. Subdivide el raster en ventanas deslizantes con `15%` de overlap.
    3. Calcula SLRM y Slope en cada celda y extrae anomalías con `confianza >= 0.70` y `dZ >= 0.20 m`.
    4. Deduplica anomalías en bordes de solapamiento y selecciona los candidatos prioritarios.
    5. Valida contra OpenStreetMap (Overpass) e IGN (WFS) para confirmar `CANDIDATO_INEDITO`.
    6. Renderiza las láminas compuestas de 4 paneles (2x2 con Blender 3D térmico) con traza dinámica sobre cada centroide exacto.
    7. Genera los dossiers técnicos INAPL (`DOSSIER_INAPL_ARQ-XXXX.md`), actualiza
       `ANEXO_CONFIDENCIAL_COORDENADAS.json` y compila `MAPA_FINAL_PROSPECCION.geojson`.
    """
    raw_dir = Path(cache_dir) if cache_dir else settings.data_dir
    proc_dir = Path(processed_dir) if processed_dir else settings.processed_dir
    rep_dir = Path(reports_dir) if reports_dir else settings.reports_dir
    raw_dir.mkdir(parents=True, exist_ok=True)
    proc_dir.mkdir(parents=True, exist_ok=True)
    rep_dir.mkdir(parents=True, exist_ok=True)

    discovered_datasets: List[Dict[str, Any]] = []
    highres_download_info: Optional[Dict[str, Any]] = None

    if hunt_highres:
        print("=" * 118)
        print("🛰️  CAZADOR AUTÓNOMO DE DATASETS LIDAR / FOTOGRAMETRÍA DE ALTA RESOLUCIÓN (0.15 m - 5.0 m) | ARGENTINA & ANDES")
        print("=" * 118)
        hunter = HighResLidarHunter(http_client=http_client)
        hunt_res = await hunter.hunt_all_sources()
        discovered_datasets = hunt_res.get("datasets", [])

        print(
            f"\n🔎 Catálogos consultados: OpenTopography API + Zenodo REST API + IGN Argentina WCS | "
            f"Total encontrados: {len(discovered_datasets)} (<= 5.0 m: {hunt_res.get('highres_count_le_5m', 0)})"
        )
        print("-" * 118)
        print(f"{'ID Dataset':<24} | {'Res (m)':<8} | {'Formato':<22} | {'Descarga':<9} | {'Título / Región'}")
        print("-" * 118)
        for d in discovered_datasets:
            dl_flag = "DIRECTA" if d.get("direct_download") else "CATÁLOGO"
            print(
                f"{str(d['id'])[:24]:<24} | {float(d['resolution_m']):<8.2f} | "
                f"{str(d['data_format'])[:22]:<22} | {dl_flag:<9} | {str(d['title'])[:52]}"
            )
        print("-" * 118)

        print("\n[FASE 1/5] Descargando el dataset de alta resolución y proyectando a POSGAR 2007 (preservando escala sub-métrica)...")
        highres_download_info = await hunter.download_best_highres_raster(
            datasets=discovered_datasets,
            out_dir=raw_dir / "highres",
            target_epsg=5344,
            max_window_px=1500,
            dataset_id=highres_id,
        )
        sel_ds = highres_download_info["selected_dataset"]
        master_dtm_path = Path(highres_download_info["posgar_tif_path"])

        ds_id_clean = str(sel_ds.get("id", "HIGHRES")).replace(":", "_").replace(".", "_").upper()
        zone_key = f"HIGHRES_{ds_id_clean}"

        dem_native_res_m = float(highres_download_info["native_resolution_m"])
        preserved_res_m = float(highres_download_info["preserved_resolution_m"])

        # Parámetros microtopográficos adaptativos para alta resolución
        if preserved_res_m < 0.15:
            adaptive_slrm_r = 2.5
            adaptive_min_area = 1.0
            adaptive_max_area = 300.0
            adaptive_min_dz = 0.10
        elif preserved_res_m <= 1.0:
            adaptive_slrm_r = 6.0
            adaptive_min_area = 4.0
            adaptive_max_area = 800.0
            adaptive_min_dz = 0.20
        else:
            adaptive_slrm_r = 12.0
            adaptive_min_area = 12.0
            adaptive_max_area = 2000.0
            adaptive_min_dz = 0.30

        zone_meta = {
            "name": f"{sel_ds['title']} ({sel_ds['region']})",
            "bbox_wgs84": sel_ds.get("bbox_wgs84", [-68.48, -34.65, -68.25, -34.55]),
            "toponyms": [sel_ds.get("region", "Argentina"), "Mendoza", "San Rafael", "Cuyo", "Andes"],
            "biome": "alta_resolucion_uav",
            "archaeo_context": (
                f"Relevamiento fotogramétrico de ultra-alta resolución con dron ({dem_native_res_m:.4f} m/px) en "
                f"{sel_ds.get('region', 'Argentina')}. Detección de alineaciones pircadas, recintos de piedra, trincheras "
                "y rasgos arqueológicos antrópicos."
            ),
            "slrm_radius_m": adaptive_slrm_r,
            "min_area_m2": adaptive_min_area,
            "max_area_m2": adaptive_max_area,
            "min_dz_m": adaptive_min_dz,
            "max_slope_deg": 35.0,
        }
        dem_source_label = f"{sel_ds['id']} - {sel_ds['title']} ({sel_ds['source']})"
        print(f"   ✔ Dataset seleccionado: {sel_ds['id']} ({sel_ds['title']})")
        print(f"   ✔ URL descargada: {sel_ds['download_url']}")
        print(
            f"   ✔ Resolución nativa: {dem_native_res_m:.4f} m/px -> "
            f"Resolución POSGAR preservada: {highres_download_info['preserved_resolution_m']:.4f} m/px "
            f"(Ventana: {highres_download_info['window_shape_px'][1]}x{highres_download_info['window_shape_px'][0]} px)"
        )
    else:
        zone_key = target_zone.upper().strip()
        zone_meta = TARGET_ZONES.get(
            zone_key,
            {
                "name": zone_key,
                "toponyms": ["Andes", "Noroeste Argentino"],
            },
        )

        print("=" * 78)
        print(f"🛰️  PROSPECCIÓN ARQUEOLÓGICA 100% AUTÓNOMA | ZONA: {zone_key}")
        print(f"📍 Región: {zone_meta.get('name', zone_key)}")
        print("=" * 78)

        # 1. Adquisición autónoma de datos de elevación reales y reproyección POSGAR 2007
        print("\n[FASE 1/5] Adquiriendo tile de elevación real (Copernicus DEM GLO-30 / AWS Open Data)...")
        master_dtm_path = Path(fetch_elevation_tile(target_zone=zone_key, cache_dir=raw_dir))
        dem_source_label = "Copernicus DEM GLO-30 (AWS Open Data)"
        dem_native_res_m = 30.0

    with rasterio.open(master_dtm_path) as src:
        crs_epsg = int(src.crs.to_epsg() or 5345)
        b = src.bounds
        master_bounds = (float(b.left), float(b.bottom), float(b.right), float(b.top))
        res_m = float(abs(src.transform.a))

    print(f"   ✔ Raster maestro validado: {master_dtm_path}")
    print(f"   ✔ Sistema Métrico: POSGAR 2007 EPSG:{crs_epsg} | Resolución: {res_m:.2f} m/px")
    print(
        f"   ✔ Extensión Métrica: E[{master_bounds[0]:.1f}, {master_bounds[2]:.1f}] "
        f"N[{master_bounds[1]:.1f}, {master_bounds[3]:.1f}]"
    )

    # Parámetros adaptativos por bioma si están definidos en la zona
    slrm_radius_m = float(zone_meta.get("slrm_radius_m") or (10.0 if res_m <= 1.0 else 24.0))
    extent_w = master_bounds[2] - master_bounds[0]
    extent_h = master_bounds[3] - master_bounds[1]
    effective_window_m = min(window_size_m, max(25.0, min(extent_w, extent_h) * 0.8)) if hunt_highres else window_size_m
    det_min_area = float(zone_meta.get("min_area_m2") or (6.0 if res_m <= 1.0 else 24.0))
    det_max_area = float(zone_meta.get("max_area_m2") or (1200.0 if res_m <= 1.0 else 4500.0))
    zone_min_dz = float(zone_meta.get("min_dz_m") or min_elevation_m)
    zone_max_slope = float(zone_meta.get("max_slope_deg") or 35.0)

    print(f"   ⚙️  Parámetros Adaptativos de Bioma [{zone_meta.get('biome', 'estándar')}]:")
    print(f"       • Radio SLRM: {slrm_radius_m:.1f} m | Área: [{det_min_area:.0f}, {det_max_area:.0f}] m²")
    print(f"       • dZ mín (abs): {zone_min_dz:.2f} m | Pendiente máx: {zone_max_slope:.0f}°")
    if zone_meta.get("archaeo_context"):
        print(f"       • Contexto: {zone_meta['archaeo_context']}")

    # Margen de borde para el detector: la tendencia SLRM está sesgada cerca del borde del
    # raster (modo 'nearest' del filtro gaussiano), así que los contornos que tocan el borde
    # del tile se descartan; el overlap del tiling garantiza la cobertura de esa franja.
    slrm_radius_px = max(2.0, slrm_radius_m / res_m) if res_m > 0 else 2.0
    border_margin_px = min(12, max(2, int(np.ceil(slrm_radius_px))))

    # Generar SLRM y Slope maestros para inspección visual continua sin costuras
    master_slrm_path = Path(
        compute_slrm(master_dtm_path, proc_dir / f"{zone_key.lower()}_master_slrm.tif", radius_m=slrm_radius_m)
    )
    master_slope_path = Path(
        compute_slope(master_dtm_path, proc_dir / f"{zone_key.lower()}_master_slope.tif")
    )

    # 2. Subdivisión (Tiling) en cuadrículas métricas con 15% de overlap
    windows = generate_sliding_windows_metric(
        bounds=master_bounds,
        window_size_m=effective_window_m,
        overlap_ratio=overlap_ratio,
    )
    print(
        f"\n[FASE 2/5] Subdivisión (Tiling): {len(windows)} celdas de "
        f"{effective_window_m:.0f}x{effective_window_m:.0f} m (overlap {overlap_ratio * 100:.0f}%)"
    )

    tiles_dir = proc_dir / "tiles" / zone_key.lower()
    tiles_dir.mkdir(parents=True, exist_ok=True)

    # Calibrador ML supervisado (probabilidad calibrada); modo degradado a score heurístico si
    # no existe el modelo entrenado (`data/processed/ml_calibrator.joblib`).
    calibrator = load_calibrator()
    if calibrator:
        print("   🤖 Calibrador ML cargado: puntuando candidatos con probabilidad calibrada (ML).")
    else:
        print("   🤖 Calibrador ML no entrenado: usando score heurístico morfológico.")

    # 3. Pipeline de Detección Celda por Celda
    print("\n[FASE 3/5] Escaneando celdas microtopográficas (SLRM + Slope + OpenCV)...")
    raw_filtered_features: List[Dict[str, Any]] = []

    for idx, (r_i, c_i, wx_min, wy_min, wx_max, wy_max) in enumerate(windows, start=1):
        cell_tag = f"C{idx:02d}_R{r_i}C{c_i}"
        cell_dtm = tiles_dir / f"{cell_tag}_dtm.tif"
        has_data = _extract_subtile_geotiff(
            src_dtm_path=master_dtm_path,
            bbox_metric=(wx_min, wy_min, wx_max, wy_max),
            out_tile_path=cell_dtm,
        )
        if not has_data:
            print(f"   [{idx:02d}/{len(windows):02d}] Celda {cell_tag}: Sin datos suficientes (omitida)")
            continue

        cell_slrm = compute_slrm(cell_dtm, tiles_dir / f"{cell_tag}_slrm.tif", radius_m=slrm_radius_m)
        cell_slope = compute_slope(cell_dtm, tiles_dir / f"{cell_tag}_slope.tif")
        cell_fc = detect_anomalies(
            cell_slrm,
            cell_slope,
            min_area=det_min_area,
            max_area=det_max_area,
            min_dz=zone_min_dz,
            max_slope_deg=zone_max_slope,
            border_margin_px=border_margin_px,
        )

        cell_feats = cell_fc.get("features", [])
        passed_cell: List[Dict[str, Any]] = []
        for feat in cell_feats:
            props = feat["properties"]
            conf = float(props["confidence"])
            mean_dz = float(props["mean_elevation_m"])
            # Probabilidad calibrada del modelo supervisado cuando está disponible.
            # - ml_mode="filter": reemplaza al score heurístico como umbral (modo estricto).
            # - ml_mode="advisory": se registra en props para priorización y contexto del
            #   Juez VLM, pero el filtro de entrada mantiene el score heurístico. Default:
            #   el calibrador actual presenta sesgo de resolución (ver ML_BENCHMARK_METRICS)
            #   y en modo filter anula todo candidato satelital (GLO-30) de zonas nuevas.
            if calibrator:
                ml_prob = score_candidate(
                    props,
                    slrm_path=master_slrm_path,
                    slope_path=master_slope_path,
                    model=calibrator,
                )
                if ml_prob is not None:
                    props["ml_probability"] = ml_prob
                    if ml_mode == "filter":
                        conf = ml_prob
            if conf >= min_confidence and abs(mean_dz) >= zone_min_dz:
                props["source_cell"] = cell_tag
                passed_cell.append(feat)

        raw_filtered_features.extend(passed_cell)
        print(
            f"   [{idx:02d}/{len(windows):02d}] Celda {cell_tag} "
            f"[E:{wx_min:.0f}-{wx_max:.0f}, N:{wy_min:.0f}-{wy_max:.0f}] -> "
            f"Detectadas: {len(cell_feats):02d} | Filtradas (conf>={min_confidence:.2f}, dZ>={zone_min_dz:.2f}m): {len(passed_cell):02d}"
        )

    # Deduplicación espacial en bordes de overlap y selección balanceada por tipología morfológica
    dedup_features = _deduplicate_candidates_metric(
        raw_filtered_features,
        crs_epsg=crs_epsg,
        min_separation_m=35.0,
    )
    # Seleccionar los mejores candidatos asegurando representación de recintos, círculos y terrazas
    by_type: Dict[str, List[Dict[str, Any]]] = {
        "recinto_ortogonal": [],
        "estructura_circular": [],
        "terraza_lineal": [],
        "estructura_hundida": [],
        "zanja_lineal": [],
    }
    for f in dedup_features:
        t = f["properties"].get("anomaly_type", "recinto_ortogonal")
        by_type.setdefault(t, []).append(f)

    selected_features: List[Dict[str, Any]] = []
    quota = max(1, max_candidates_to_validate // 3)
    for t_key in ("recinto_ortogonal", "estructura_circular", "terraza_lineal", "estructura_hundida", "zanja_lineal"):
        selected_features.extend(by_type.get(t_key, [])[:quota])
    for f in dedup_features:
        if len(selected_features) >= max_candidates_to_validate:
            break
        if f not in selected_features:
            selected_features.append(f)

    print(
        f"\n   ✔ Total bruto tras filtro: {len(raw_filtered_features)} | "
        f"Únicos deduplicados: {len(dedup_features)} | "
        f"Priorizados para validación profunda: {len(selected_features)}"
    )

    # 4. Validación Automática (IGN WFS + Overpass OSM + OpenAlex) e Inspección Visual Dinámica
    print("\n[FASE 4/5] Validando candidatos contra Catastro IGN (WFS), OpenStreetMap (Overpass) y Literatura...")
    to_metric = Transformer.from_crs(CRS.from_epsg(4326), CRS.from_epsg(crs_epsg), always_xy=True)

    # Consultar literatura académica una vez por zona con sus topónimos
    z_bbox = zone_meta.get("bbox") or zone_meta.get("bbox_wgs84", (-65.96, -24.45, -65.95, -24.44))
    center_lon = (z_bbox[0] + z_bbox[2]) / 2.0
    center_lat = (z_bbox[1] + z_bbox[3]) / 2.0
    zone_papers = await check_academic_papers(
        lat=center_lat,
        lon=center_lon,
        toponyms=list(zone_meta.get("toponyms", [zone_meta.get("name", "Arqueologia")])),
        http_client=http_client,
    )

    confirmed_features: List[Dict[str, Any]] = []
    candidates_report_rows: List[Dict[str, Any]] = []
    vlm_discards: Dict[str, Any] = {}

    for seq_idx, feat in enumerate(selected_features, start=1):
        if zone_key == "ZONA_1_TASTIL":
            cand_id = f"ARQ-{seq_idx:04d}"
        elif hunt_highres or zone_key.startswith("HIGHRES"):
            tag = "HRM" if "3383227" in zone_key else "HR2"
            cand_id = f"ARQ-{tag}-{seq_idx:04d}"
        else:
            zone_short_map = {
                "ZONA_2_YOCAVIL": "YOC",
                "ZONA_3_TINOGASTA": "TIN",
                "ZONA_4_TOLOMBON": "TOL",
                "ZONA_5_LAPAYA": "PAY",
                "ZONA_6_TILCARA": "TIL",
                "ZONA_7_ACONQUIJA": "ACO",
                "ZONA_8_SHINCAL": "SHI",
                "ZONA_9_ALUMBRERA": "ALU",
                "ZONA_10_RINCONADA": "RIN",
                "ZONA_11_LACUEVA": "CUE",
                "ZONA_12_USPALLATA": "USP",
                "ZONA_13_SOMUNCURA": "SOM",
                "ZONA_14_LLULLAILLACO": "LLU",
                "ZONA_15_VOLCAN_GALAN": "GAL",
                "ZONA_16_LAGO_BUENOS_AIRES": "LBA",
                "ZONA_17_VOLCAN_CHANI": "CHA",
                "ZONA_17_CHANI": "CHA",
                "ZONA_18_FAMATINA": "FAM",
                "ZONA_19_ACHALA": "ACH",
                "ZONA_20_VALLE_GRANDE": "VGR",
                "ZONA_21_CIUDACITA": "CIU",
                "ZONA_22_TEYU_CUARE": "TEY",
                "ZONA_23_DELTA_PARANA": "DEL",
                "ZONA_24_IBERA": "IBE",
                "ZONA_25_ANSENUZA": "ANS",
                "ZONA_26_STROBEL": "STR",
                "ZONA_27_PIEDRA_PARADA": "PPA",
                "ZONA_28_PAYUNIA": "PYU",
                "ZONA_29_SIERRA_DE_MANCHAO": "MAN",
            }
            zone_short = zone_short_map.get(zone_key, zone_key.split("_")[-1][:3].upper())
            cand_id = f"ARQ-{zone_short}-{seq_idx:04d}"
        props = feat["properties"]
        props["id"] = cand_id
        feat["id"] = cand_id

        lon_w, lat_w = float(props["centroid_wgs84"][0]), float(props["centroid_wgs84"][1])
        val_res = await validate_anomaly_async(
            lat=lat_w,
            lon=lon_w,
            anomaly_id=cand_id,
            http_client=http_client,
        )

        props["classification"] = val_res.classification
        props["distance_to_water_m"] = val_res.distance_to_water_m
        props["ign_matches_count"] = len(val_res.ign_matches)
        props["osm_matches_count"] = len(val_res.osm_matches)
        props["academic_references_count"] = len(zone_papers)

        # Vigilancia patrimonial: patrón compatible con pozo de huaquero cerca de un sitio registrado
        looting_alert = evaluate_looting_alert(
            props,
            osm_matches=val_res.osm_matches,
            ign_matches=val_res.ign_matches,
        )
        if looting_alert:
            props["patrimonial_priority"] = looting_alert["alert"]
            props["nearest_known_site"] = looting_alert["nearest_known_site"]
            props["diameter_m"] = looting_alert["diameter_m"]
            props["looting_osm_context"] = looting_alert["osm_historic_context"]
            props["looting_ign_context"] = looting_alert["ign_settlement_context"]
            site_name = (looting_alert["nearest_known_site"] or {}).get("name", "contexto IGN/OSM")
            print(
                f"      🚨 {looting_alert['alert']} (diam. {looting_alert['diameter_m']} m, "
                f"sitio: {site_name}) — vía de denuncia Ley 25.743"
            )

        print(
            f"   -> {cand_id} ({props['anomaly_type']}, {props['area_m2']} m², dZ={props['mean_elevation_m']:+.2f} m) "
            f"=> Clasificación: {val_res.classification}"
        )

        if val_res.classification == "CANDIDATO_INEDITO":
            # Calcular BBOX y centroide exacto en POSGAR 2007 para la lámina dinámica (compatible con Polygon y MultiPolygon)
            geom_obj = shape(feat["geometry"])
            g_min_lon, g_min_lat, g_max_lon, g_max_lat = geom_obj.bounds
            min_x, min_y = to_metric.transform(float(g_min_lon), float(g_min_lat))
            max_x, max_y = to_metric.transform(float(g_max_lon), float(g_max_lat))
            cx_m, cy_m = to_metric.transform(lon_w, lat_w)
            bbox_posgar = [min(min_x, max_x), min(min_y, max_y), max(min_x, max_x), max(min_y, max_y)]

            composite_png_path = proc_dir / f"{zone_key.lower()}_{cand_id}_composite.png"
            render_candidate_composite(
                dtm_path=master_dtm_path,
                slrm_path=master_slrm_path,
                bbox_posgar=bbox_posgar,
                out_png_path=composite_png_path,
                centroid_posgar=[cx_m, cy_m],
                buffer_m=6.0 if res_m <= 0.15 else (10.0 if res_m <= 1.0 else 15.0),
                candidate_id=cand_id,
            )

            # Juicio pericial multimodal (Gemini si hay clave; si no, PENDIENTE_REVISION / caché del agente MCP)
            props["biome"] = zone_meta.get("biome", "general")
            props["archaeo_context"] = zone_meta.get("archaeo_context", "")
            props["dem_source"] = dem_source_label
            props["dem_native_resolution_m"] = dem_native_res_m
            props["dem_processing_resolution_m"] = res_m
            props["composite_image_path"] = str(composite_png_path)
            vlm_verdict = evaluate_candidate_with_vlm(
                cand_id,
                composite_png_path,
                props,
                cache_dir=proc_dir / "vlm_cache",
            )
            props["vlm_verdict"] = vlm_verdict
            print(
                f"      🧠 VLM [{vlm_verdict['backend']}]: {vlm_verdict['verdict']} "
                f"({vlm_verdict['certainty_pct']}%) - {vlm_verdict['functional_interpretation']}"
            )

            thermal_3d_candidate = proc_dir / f"{cand_id}_3d_thermal.png"
            dossier_payload: Dict[str, Any] = {
                "id": cand_id,
                "anomaly_type": props["anomaly_type"],
                "classification": val_res.classification,
                "confidence": props["confidence"],
                "area_m2": props["area_m2"],
                "rectangularity": props["rectangularity"],
                "circularity": props["circularity"],
                "mean_elevation_m": props["mean_elevation_m"],
                "distance_to_water_m": val_res.distance_to_water_m,
                "centroid_wgs84": [lon_w, lat_w],
                "bbox_posgar": [round(v, 2) for v in bbox_posgar],
                "geometry_geojson": feat["geometry"],
                "crs_epsg": f"EPSG:{crs_epsg}",
                "biome": props["biome"],
                "archaeo_context": props["archaeo_context"],
                "composite_image_path": str(composite_png_path),
                "thermal_3d_image_path": str(thermal_3d_candidate) if thermal_3d_candidate.exists() else None,
                "vlm_verdict": vlm_verdict,
            }
            dossier_md_path = generate_inapl_dossier(dossier_payload, out_dir=rep_dir)

            props["dossier_path"] = str(dossier_md_path)
            if vlm_verdict["verdict"] in DISCARD_VERDICTS:
                vlm_discards[cand_id] = {
                    "anomaly_type": props["anomaly_type"],
                    "area_m2": props["area_m2"],
                    "mean_elevation_m": props["mean_elevation_m"],
                    "composite_image_path": str(composite_png_path),
                    "dossier_path": str(dossier_md_path),
                    "vlm_verdict": vlm_verdict,
                }
                continue
            confirmed_features.append(feat)

            candidates_report_rows.append(
                {
                    "id": cand_id,
                    "source_cell": props.get("source_cell", "N/A"),
                    "anomaly_type": props["anomaly_type"],
                    "confidence": props["confidence"],
                    "area_m2": props["area_m2"],
                    "mean_elevation_m": props["mean_elevation_m"],
                    "rectangularity": props["rectangularity"],
                    "circularity": props["circularity"],
                    "distance_to_water_m": val_res.distance_to_water_m,
                    "composite_image_path": str(composite_png_path),
                    "dossier_path": str(dossier_md_path),
                    "vlm_verdict": vlm_verdict["verdict"],
                }
            )

    if vlm_discards:
        disc_path = rep_dir / "DESCARTES_VLM.json"
        disc: Dict[str, Any] = {"discarded": {}}
        if disc_path.exists():
            try:
                loaded = json.loads(disc_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict) and "discarded" in loaded:
                    disc["discarded"] = loaded["discarded"]
            except Exception:
                pass
        disc["updated_at_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        disc["discarded"].update(vlm_discards)
        disc_path.write_text(json.dumps(disc, indent=2, ensure_ascii=False), encoding="utf-8")

    # 5. Compilación de MAPA_PROSPECCION_{zone_key}.geojson y merge en MAPA_FINAL_PROSPECCION.geojson
    print("\n[FASE 5/5] Generando entregables patrimoniales y mapas GeoJSON...")
    zone_geojson_path = rep_dir / f"MAPA_PROSPECCION_{zone_key}.geojson"
    zone_fc: Dict[str, Any] = {
        "type": "FeatureCollection",
        "metadata": {
            "project": "ArchaeoLiDAR-AR-MCP Autonomous Prospector",
            "target_zone": zone_key,
            "region_name": zone_meta.get("name", zone_key),
            "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "metric_crs": f"EPSG:{crs_epsg}",
            "output_crs": "EPSG:4326",
            "windows_scanned": len(windows),
            "confirmed_inedito_count": len(confirmed_features),
            "academic_papers_found": len(zone_papers),
        },
        "features": confirmed_features,
    }
    zone_geojson_path.write_text(json.dumps(zone_fc, indent=2, ensure_ascii=False), encoding="utf-8")

    final_geojson_path = rep_dir / "MAPA_FINAL_PROSPECCION.geojson"
    existing_features: List[Dict[str, Any]] = []
    if final_geojson_path.exists():
        try:
            old_fc = json.loads(final_geojson_path.read_text(encoding="utf-8"))
            for ef in old_fc.get("features", []):
                ef_id = ef.get("id") or ef.get("properties", {}).get("id")
                if not any((cf.get("id") or cf.get("properties", {}).get("id")) == ef_id for cf in confirmed_features):
                    existing_features.append(ef)
        except Exception:
            pass

    combined_features = existing_features + confirmed_features
    final_fc: Dict[str, Any] = {
        "type": "FeatureCollection",
        "metadata": {
            "project": "ArchaeoLiDAR-AR-MCP Autonomous Prospector",
            "last_scanned_zone": zone_key,
            "region_name": zone_meta.get("name", zone_key),
            "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "output_crs": "EPSG:4326",
            "confirmed_inedito_count": len(combined_features),
        },
        "features": combined_features,
    }
    final_geojson_path.write_text(json.dumps(final_fc, indent=2, ensure_ascii=False), encoding="utf-8")

    annex_path = rep_dir / "ANEXO_CONFIDENCIAL_COORDENADAS.json"
    print(f"   ✔ Mapa final GeoJSON compilado: {final_geojson_path} ({len(confirmed_features)} candidatos inéditos)")
    print(f"   ✔ Anexo confidencial actualizado: {annex_path}")
    print("=" * 78)

    return {
        "status": "success",
        "target_zone": zone_key,
        "master_dtm_path": str(master_dtm_path),
        "master_slrm_path": str(master_slrm_path),
        "master_slope_path": str(master_slope_path),
        "crs_epsg": crs_epsg,
        "windows_scanned": len(windows),
        "confirmed_count": len(confirmed_features),
        "candidates": candidates_report_rows,
        "final_map_geojson": str(final_geojson_path),
        "confidential_annex_json": str(annex_path),
        "discovered_highres_datasets": discovered_datasets,
        "highres_download_info": highres_download_info,
    }


def _parse_cli_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ejecuta la Prospección Arqueológica 100% Autónoma (Zero Human-in-the-Loop)."
    )
    parser.add_argument(
        "--target",
        type=str,
        default="ZONA_1_TASTIL",
        choices=list(TARGET_ZONES.keys()),
        help="Zona arqueológica objetivo del NOA (por defecto: ZONA_1_TASTIL).",
    )
    parser.add_argument(
        "--all-zones",
        action="store_true",
        help="Ejecuta la prospección autónoma sobre todas las zonas configuradas en TARGET_ZONES.",
    )
    parser.add_argument(
        "--new-zones-only",
        action="store_true",
        help="Ejecuta la prospección autónoma sobre las nuevas zonas añadidas (ZONA_4 a ZONA_13).",
    )
    parser.add_argument(
        "--hunt-highres",
        action="store_true",
        help="Busca y descarga autónomamente datasets LiDAR/UAV de alta resolución (0.15 m a 5.0 m) en Argentina y los Andes.",
    )
    parser.add_argument(
        "--highres-id",
        type=str,
        default=None,
        help="ID específico del dataset LiDAR/UAV a procesar (ej. 'ZENODO:3383227').",
    )
    parser.add_argument(
        "--window-size",
        type=float,
        default=500.0,
        help="Tamaño de ventana deslizante en metros (por defecto: 500.0 m).",
    )
    parser.add_argument(
        "--overlap",
        type=float,
        default=0.15,
        help="Solapamiento entre celdas (por defecto: 0.15).",
    )
    parser.add_argument(
        "--max-candidates",
        type=int,
        default=10,
        help="Cantidad máxima de candidatos deduplicados a procesar e inspeccionar (por defecto: 10).",
    )
    parser.add_argument(
        "--reevaluate-only",
        action="store_true",
        help="Re-evalúa únicamente las láminas existentes con el Juez Pericial VLM sin re-escanear celdas.",
    )
    parser.add_argument(
        "--ml-mode",
        type=str,
        default="advisory",
        choices=["advisory", "filter"],
        help=(
            "Uso del calibrador ML: 'advisory' (default) registra ml_probability pero filtra con "
            "el score heurístico; 'filter' usa la probabilidad ML como umbral de entrada (estricto)."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_cli_args()

    if args.hunt_highres or args.highres_id:
        target_list = ["HIGHRES"]
    elif args.all_zones:
        target_list = list(TARGET_ZONES.keys())
    elif args.new_zones_only:
        target_list = [k for k in TARGET_ZONES.keys() if k not in {"ZONA_1_TASTIL", "ZONA_2_YOCAVIL", "ZONA_3_TINOGASTA"}]
    else:
        target_list = [args.target]

    all_summaries: List[Dict[str, Any]] = []

    for z_name in target_list:
        summary = asyncio.run(
            run_autonomous_prospector(
                target_zone=z_name if z_name != "HIGHRES" else "ZONA_1_TASTIL",
                window_size_m=args.window_size,
                overlap_ratio=args.overlap,
                max_candidates_to_validate=args.max_candidates,
                ml_mode=args.ml_mode,
                hunt_highres=bool(args.hunt_highres or args.highres_id),
                highres_id=args.highres_id,
            )
        )
        all_summaries.append(summary)

    disc_path = Path(settings.reports_dir) / "DESCARTES_VLM.json"
    if disc_path.exists():
        disc_data = json.loads(disc_path.read_text(encoding="utf-8")).get("discarded", {})
        if disc_data:
            print(f"\n🧹 CANDIDATOS DESCARTADOS POR EL JUEZ PERICIAL VLM ({len(disc_data)} filtrados como NATURAL/ARTEFACTO):")
            print("-" * 118)
            print(f"{'ID':<10} | {'Veredicto VLM':<12} | {'Certeza':<8} | {'Área (m²)':<10} | {'dZ (m)':<8} | {'Interpretación Pericial'}")
            print("-" * 118)
            for cid, d in disc_data.items():
                v = d["vlm_verdict"]
                print(
                    f"{cid:<10} | {v['verdict']:<12} | {v['certainty_pct']:>5}%   | "
                    f"{d['area_m2']:<10.2f} | {d['mean_elevation_m']:<+8.3f} | "
                    f"{v['functional_interpretation'][:58]}"
                )
            print("-" * 118)

    print("\n📋 TABLA DE RESUMEN DE CANDIDATOS INÉDITOS SOBREVIVIENTES (ANTROPICA / PENDIENTE)")
    print("-" * 118)
    surviving_candidates = [c for s in all_summaries for c in s.get("candidates", [])]
    if not surviving_candidates:
        print("   [0 candidatos antrópicos sobrevivientes — Todos los falsos positivos geomorfológicos/interpolación fueron filtrados]")
    else:
        print(f"{'ID':<10} | {'Celda':<10} | {'Tipología':<22} | {'VLM':<18} | {'Área (m²)':<10} | {'dZ (m)':<8} | {'Lámina Compuesta'}")
        print("-" * 118)
        for c in surviving_candidates:
            print(
                f"{c['id']:<10} | {c['source_cell']:<10} | {c['anomaly_type']:<22} | "
                f"{c.get('vlm_verdict', 'N/A'):<18} | {c['area_m2']:<10.2f} | {c['mean_elevation_m']:<+8.3f} | "
                f"{c['composite_image_path']}"
            )
    print("-" * 118)


if __name__ == "__main__":
    main()
