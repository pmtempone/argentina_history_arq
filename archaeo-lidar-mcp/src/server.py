"""Servidor FastMCP principal para ArchaeoLiDAR-AR-MCP: exposición de herramientas autónomas."""

from pathlib import Path
from typing import Any, Dict, List

from fastmcp import FastMCP

from src.config import settings
from src.core.anomaly_detector import detect_anomalies
from src.core.lidar_processor import lidar_to_dtm
from src.core.literature_checker import check_academic_papers
from src.core.relief_models import compute_relief_pipeline
from src.core.report_generator import generate_inapl_dossier
from src.core.spatial_validator import validate_anomaly_async
from src.core.visual_inspector import (
    render_candidate_composite,
    render_pointcloud_cross_section,
)
from src.schemas import CrossSectionResult, DTMResult, ReliefResult, ValidationResult

mcp = FastMCP(
    "ArchaeoLiDAR-AR-MCP",
    instructions=(
        "Servidor especializado en prospección y detección autónoma de sitios arqueológicos en Argentina "
        "mediante procesamiento de nubes LiDAR (PDAL), modelos de relieve local (SLRM y Slope), "
        "visión artificial (OpenCV), inspección multimodal de perfiles de nubes crudas y validación "
        "cruzada con el IGN (WFS), OpenStreetMap (Overpass) y literatura académica (OpenAlex). "
        "Todas las mediciones métricas se ejecutan en fajas POSGAR 2007 (EPSG:5343 a EPSG:5349)."
    ),
)


@mcp.tool()
def tool_process_lidar_dtm(las_path: str, resolution: float = 0.5) -> DTMResult:
    """Procesa un archivo LiDAR (.las/.laz) crudo y genera un Modelo Digital del Terreno (DTM) en POSGAR 2007.

    Aplica automáticamente el filtro morfológico SMRF (`filters.smrf`) calibrado para vegetación
    arbustiva/monte de Argentina si la nube carece de clasificación de suelo, filtra los retornos
    de suelo desnudo (ASPRS Clase 2) e interpola un GeoTIFF Float32 mediante IDW (`writers.gdal`).

    Args:
        las_path: Ruta al archivo `.las` o `.laz` de entrada.
        resolution: Resolución espacial del DTM de salida en metros (por defecto 0.5 m).

    Returns:
        `DTMResult` con el estado, ruta al GeoTIFF generado, código EPSG POSGAR 2007, resolución,
        extensión métrica y cantidad de puntos de suelo procesados.
    """
    settings.ensure_directories()
    in_path = Path(las_path)
    out_dtm = settings.processed_dir / f"{in_path.stem}_dtm.tif"
    return lidar_to_dtm(las_path=in_path, out_dtm_path=out_dtm, resolution=resolution)


@mcp.tool()
def tool_compute_relief_models(dtm_path: str, radius_m: float = 10.0) -> ReliefResult:
    """Calcula el Simple Local Relief Model (SLRM) y el mapa de pendientes (Slope) desde un DTM.

    Garantiza que el raster esté proyectado en metros (POSGAR 2007), reemplaza valores `nodata` con
    `np.nan` antes de realizar la convolución gaussiana para evitar artefactos en los bordes y
    genera dos GeoTIFF Float32: `SLRM` (diferencia respecto a la tendencia topográfica local) y
    `Slope` (pendiente en grados sexagesimales).

    Args:
        dtm_path: Ruta al archivo GeoTIFF del DTM de entrada.
        radius_m: Radio del filtro de tendencia local en metros (por defecto 10.0 m).

    Returns:
        `ReliefResult` con las rutas a los archivos SLRM y Slope y un diccionario de estadísticas.
    """
    settings.ensure_directories()
    return compute_relief_pipeline(dtm_path=dtm_path, out_dir=settings.processed_dir, radius_m=radius_m)


@mcp.tool()
def tool_detect_anomalies(slrm_path: str, slope_path: str) -> dict:
    """Detecta anomalías microtopográficas arqueológicas sobre los modelos SLRM y Slope usando OpenCV.

    Aísla sobreelevaciones locales entre 0.15 m y 3.0 m en terrenos con pendiente menor o igual a 35°,
    aplica filtro bilateral, umbral adaptativo y clausura morfológica, extrae contornos poligonales y
    clasifica cada estructura en `recinto_ortogonal`, `estructura_circular` o `terraza_lineal`.
    Además agrupa estructuras cercanas (< 80 m) mediante un árbol espacial `cKDTree` para identificar
    complejos arquitectónicos y reproyecta las geometrías finales a `EPSG:4326` (WGS84).

    Args:
        slrm_path: Ruta al GeoTIFF del Simple Local Relief Model (SLRM).
        slope_path: Ruta al GeoTIFF de pendiente en grados.

    Returns:
        Diccionario GeoJSON `FeatureCollection` con las anomalías detectadas y sus descriptores geométricos.
    """
    return detect_anomalies(slrm_path=slrm_path, slope_path=slope_path)


@mcp.tool()
def tool_inspect_candidate(
    dtm_path: str,
    slrm_path: str,
    bbox: list[float],
    centroid: list[float] | None = None,
    buffer_m: float = 15.0,
) -> str:
    """Renderiza una lámina de inspección multimodal de 3 paneles para evaluar un candidato arqueológico.

    Genera una imagen PNG de alta resolución compuesta por:
    1. Hillshade multidireccional con exageración vertical 1.5x y traza que cruza el centroide exacto.
    2. Simple Local Relief Model (SLRM) con paleta de contraste `viridis`.
    3. Perfil topográfico 2D sobre la traza dinámica atravesando el centroide exacto hacia los extremos
       del bounding box extendido en 15 metros, resaltando en naranja las zonas elevadas (>= 0.15 m).

    Args:
        dtm_path: Ruta al GeoTIFF del DTM en coordenadas métricas POSGAR 2007.
        slrm_path: Ruta al GeoTIFF del SLRM en coordenadas métricas POSGAR 2007.
        bbox: Lista de 4 flotantes `[minx, miny, maxx, maxy]` en coordenadas métricas POSGAR 2007.
        centroid: Lista opcional de 2 flotantes `[cx, cy]` en coordenadas métricas POSGAR 2007.
        buffer_m: Margen métrico de extensión del bounding box en metros (por defecto 15.0 m).

    Returns:
        Ruta como string a la imagen PNG compuesta generada.
    """
    settings.ensure_directories()
    stem = Path(dtm_path).stem
    out_png = settings.processed_dir / f"{stem}_candidate_composite.png"
    return render_candidate_composite(
        dtm_path=dtm_path,
        slrm_path=slrm_path,
        bbox_posgar=bbox,
        out_png_path=out_png,
        centroid_posgar=centroid,
        buffer_m=buffer_m,
    )


@mcp.tool()
def tool_verify_cross_section(las_path: str, p1: list[float], p2: list[float]) -> CrossSectionResult:
    """Extrae y grafica un corte transversal (cross-section) directo sobre la nube de puntos cruda.

    Corta una franja (swath) de 2.0 m de ancho entre los puntos `p1` y `p2`, separa retornos de
    vegetación (ASPRS Clases 3, 4 y 5 en verde semitransparente) y retornos de suelo (ASPRS Clase 2
    en marrón sólido), y calcula la densidad efectiva de puntos de suelo por metro cuadrado junto
    con el puntaje de integridad del perfil para descartar falsas anomalías por vacíos de interpolación.

    Args:
        las_path: Ruta al archivo de nube de puntos `.las/.laz` (o `.npz`/`.tif` de respaldo).
        p1: Coordenadas métricas POSGAR `[x1, y1]` del inicio de la traza.
        p2: Coordenadas métricas POSGAR `[x2, y2]` del fin de la traza.

    Returns:
        `CrossSectionResult` con la ruta al gráfico PNG, conteos de puntos, densidad e integridad.
    """
    settings.ensure_directories()
    stem = Path(las_path).stem
    out_png = settings.processed_dir / f"{stem}_cross_section.png"
    return render_pointcloud_cross_section(
        las_path=las_path,
        p1_xy=p1,
        p2_xy=p2,
        swath_width_m=2.0,
        out_png_path=out_png,
    )


@mcp.tool()
async def tool_validate_candidate(lat: float, lon: float) -> ValidationResult:
    """Realiza la validación espacial y bibliográfica cruzada de un candidato en coordenadas WGS84.

    Consulta de forma asíncrona:
    1. Servicio WFS del Instituto Geográfico Nacional (IGN Argentina) en un entorno de ±0.005° para
       infraestructura y la capa `ign:linea_de_agua` (calculando la distancia métrica exacta al agua
       en POSGAR 2007).
    2. Overpass API (OpenStreetMap) en un radio de 150 m buscando `historic=*`, `barrier=wall|fence`
       y `building=*`.
    3. Capa GeoPackage local de sitios arqueológicos registrados y búsqueda académica en OpenAlex.

    Args:
        lat: Latitud geográfica en grados decimales (WGS84).
        lon: Longitud geográfica en grados decimales (WGS84).

    Returns:
        `ValidationResult` con la clasificación (`CANDIDATO_INEDITO`, `SITIO_REGISTRADO` o
        `FALSO_POSITIVO_MODERNO`), coincidencias IGN/OSM/literatura y distancia al agua en metros.
    """
    val_res = await validate_anomaly_async(lat=lat, lon=lon)
    # Enriquecer con búsqueda bibliográfica si hay topónimos en los resultados de IGN/OSM
    toponyms: List[str] = []
    for m in val_res.ign_matches:
        props = m.get("properties", {}) or {}
        for key in ("nombre", "nam", "fna", "toponimo"):
            if props.get(key):
                toponyms.append(str(props[key]))
    for m in val_res.osm_matches:
        tags = m.get("tags", {}) or {}
        if tags.get("name"):
            toponyms.append(str(tags["name"]))

    papers = await check_academic_papers(lat=lat, lon=lon, toponyms=toponyms)
    return ValidationResult(
        anomaly_id=val_res.anomaly_id,
        classification=val_res.classification,
        ign_matches=val_res.ign_matches,
        osm_matches=val_res.osm_matches,
        literature_matches=papers,
        distance_to_water_m=val_res.distance_to_water_m,
    )


@mcp.tool()
def tool_generate_dossier(candidate_id: str, report_data: dict) -> str:
    """Genera el Dossier Técnico para el INAPL (Ley 25.743) y aísla las coordenadas confidenciales.

    Produce un informe técnico en Markdown listo para presentación ante autoridades patrimoniales y
    separa las coordenadas exactas en `ANEXO_CONFIDENCIAL_COORDENADAS.json` para prevenir el saqueo
    arqueológico (*guaqueo*).

    Args:
        candidate_id: Identificador único del candidato (ej. `'ARQ-0001'`).
        report_data: Diccionario con las métricas geométricas, validación espacial y rutas de imágenes.

    Returns:
        Ruta como string al archivo Markdown del dossier técnico generado.
    """
    settings.ensure_directories()
    payload: Dict[str, Any] = dict(report_data)
    payload["id"] = candidate_id
    return generate_inapl_dossier(candidate_data=payload, out_dir=settings.reports_dir)


@mcp.tool()
async def tool_run_full_pipeline(
    input_path: str,
    resolution: float = 0.5,
    radius_m: float = 10.0,
    known_gpkg_path: str | None = None,
) -> dict:
    """Ejecuta el pipeline autónomo completo: entrada (.las/.laz o .tif) -> DTM -> SLRM/Slope -> CV -> Láminas -> Validación -> Dossier INAPL.

    Pipeline unificado de prospección:
    1. Si es archivo LiDAR (.las/.laz), aplica filtro SMRF para monte argentino y genera DTM en POSGAR 2007.
    2. Calcula SLRM (convolución libre de NaNs) y mapa de pendientes en grados sexagesimales.
    3. Detecta anomalías microtopográficas, clasifica geometrías (pircas, chenques, terrazas) y agrupa complejos arquitectónicos (< 80 m).
    4. Genera para cada candidato una lámina compuesta de 3 paneles con traza dinámica atravesando su centroide exacto.
    5. Realiza validación espacial contra IGN (WFS), Overpass (OSM) y literatura académica (OpenAlex).
    6. Redacta el dossier técnico INAPL (Ley 25.743) y resguarda las coordenadas sensibles en ANEXO_CONFIDENCIAL_COORDENADAS.json.

    Args:
        input_path: Ruta al archivo LiDAR (.las/.laz) o raster DTM (.tif) en coordenadas POSGAR o WGS84.
        resolution: Resolución espacial de celda en metros (por defecto 0.5 m).
        radius_m: Radio del filtro de tendencia local en metros para el SLRM (por defecto 10.0 m).
        known_gpkg_path: Ruta opcional a un archivo GeoPackage local con sitios arqueológicos registrados.

    Returns:
        Diccionario con el resumen de ejecución, lista de candidatos detectados, láminas generadas y dossiers INAPL.
    """
    from pyproj import CRS, Transformer
    import rasterio
    from src.core.looting_monitor import evaluate_looting_alert
    from src.core.ml_calibrator import load_calibrator, score_candidate
    from src.core.optical_providers import fetch_candidate_optical_context
    from src.core.vlm_judge import evaluate_candidate_with_vlm

    settings.ensure_directories()
    calibrator = load_calibrator()
    src_file = Path(input_path)
    if not src_file.exists():
        raise FileNotFoundError(f"No se encontró el archivo de entrada: {input_path}")

    # 1. Obtener DTM (procesar LiDAR o asegurar proyección métrica si ya es raster)
    if src_file.suffix.lower() in {".las", ".laz"}:
        dtm_res = lidar_to_dtm(
            las_path=src_file,
            out_dtm_path=settings.processed_dir / f"{src_file.stem}_dtm.tif",
            resolution=resolution,
        )
        dtm_path = dtm_res.dtm_path
        target_epsg = dtm_res.crs_epsg
    else:
        from src.core.crs_manager import ensure_metric_crs
        dtm_path = ensure_metric_crs(
            src_file,
            settings.processed_dir / f"{src_file.stem}_posgar.tif",
        )
        with rasterio.open(dtm_path) as s:
            target_epsg = s.crs.to_epsg() or 5344

    # 2. Calcular modelos de relieve (SLRM y Slope)
    relief_res = compute_relief_pipeline(
        dtm_path=dtm_path,
        out_dir=settings.processed_dir,
        radius_m=radius_m,
    )

    # 3. Detección morfológica de anomalías con OpenCV y clustering espacial
    anomalies_fc = detect_anomalies(
        slrm_path=relief_res.slrm_path,
        slope_path=relief_res.slope_path,
    )

    to_metric = Transformer.from_crs(CRS.from_epsg(4326), CRS.from_epsg(target_epsg), always_xy=True)
    candidates_summary: List[Dict[str, Any]] = []
    features = anomalies_fc.get("features", [])

    for feat in features:
        props = feat.get("properties", {})
        cand_id = props.get("id", "ARQ-0001")
        centroid_wgs = props.get("centroid_wgs84", [-65.0, -24.0])
        lon_w, lat_w = float(centroid_wgs[0]), float(centroid_wgs[1])

        # Extraer bounding box métrico del polígono en POSGAR 2007
        coords_wgs = feat.get("geometry", {}).get("coordinates", [[]])[0]
        if coords_wgs:
            metric_ring = [to_metric.transform(x, y) for x, y in coords_wgs]
            xs = [p[0] for p in metric_ring]
            ys = [p[1] for p in metric_ring]
            min_x, max_x = min(xs), max(xs)
            min_y, max_y = min(ys), max(ys)
        else:
            cand_cx, cand_cy = to_metric.transform(lon_w, lat_w)
            min_x, max_x = cand_cx - 20.0, cand_cx + 20.0
            min_y, max_y = cand_cy - 20.0, cand_cy + 20.0

        cand_cx, cand_cy = to_metric.transform(lon_w, lat_w)

        # 4. Validación espacial cruzada IGN + OSM + GPKG y vigilancia de saqueo
        val_res = await validate_anomaly_async(
            lat=lat_w,
            lon=lon_w,
            known_gpkg_path=known_gpkg_path,
            anomaly_id=cand_id,
        )

        # 5. Calibrador ML supervisado y alerta patrimonial ALERTA_SAQUEO
        ml_prob = None
        if calibrator:
            ml_prob = score_candidate(
                props,
                slrm_path=relief_res.slrm_path,
                slope_path=relief_res.slope_path,
                model=calibrator,
            )
            if ml_prob is not None:
                props["ml_probability"] = ml_prob

        looting_alert = evaluate_looting_alert(
            props,
            osm_matches=val_res.osm_matches,
            ign_matches=val_res.ign_matches,
        )

        # 6. Contexto óptico/multiespectral (solo para CANDIDATO_INEDITO) + lámina compuesta
        optical_ctx = None
        if val_res.classification == "CANDIDATO_INEDITO":
            optical_ctx = fetch_candidate_optical_context(
                candidate_id=cand_id,
                centroid_wgs84=centroid_wgs,
                bbox_posgar=[min_x, min_y, max_x, max_y],
                crs_epsg=target_epsg,
                out_dir=settings.processed_dir,
                geometry_wgs84=feat.get("geometry"),
            )

        composite_path = settings.processed_dir / f"{src_file.stem}_{cand_id}_composite.png"
        render_candidate_composite(
            dtm_path=dtm_path,
            slrm_path=relief_res.slrm_path,
            bbox_posgar=[min_x, min_y, max_x, max_y],
            out_png_path=composite_path,
            centroid_posgar=[cand_cx, cand_cy],
            buffer_m=15.0,
            candidate_id=cand_id,
            optical_context=optical_ctx,
        )

        # 7. Búsqueda académica y evaluación VLM
        papers = await check_academic_papers(
            lat=lat_w,
            lon=lon_w,
            toponyms=[cand_id],
        )

        vlm_metrics: Dict[str, Any] = dict(props)
        vlm_metrics["dem_processing_resolution_m"] = resolution
        if optical_ctx:
            vlm_metrics["optical_provider_used"] = optical_ctx.get("optical_provider_used")
            vlm_metrics["ndvi_mean"] = optical_ctx.get("ndvi_mean")
            vlm_metrics["ndvi_anomaly_delta"] = optical_ctx.get("ndvi_anomaly_delta")
            vlm_metrics["ndwi_mean"] = optical_ctx.get("ndwi_mean")
        if looting_alert:
            vlm_metrics["patrimonial_priority"] = looting_alert["alert"]
            vlm_metrics["nearest_known_site"] = looting_alert["nearest_known_site"]
            vlm_metrics["diameter_m"] = looting_alert["diameter_m"]

        vlm_verdict = evaluate_candidate_with_vlm(
            cand_id,
            composite_path,
            vlm_metrics,
            cache_dir=settings.processed_dir / "vlm_cache",
        )

        # 8. Generación de dossier técnico INAPL y resguardo de coordenadas
        report_payload = {
            "id": cand_id,
            "anomaly_type": props.get("anomaly_type"),
            "classification": val_res.classification,
            "confidence": props.get("confidence"),
            "ml_probability": ml_prob,
            "area_m2": props.get("area_m2"),
            "rectangularity": props.get("rectangularity"),
            "circularity": props.get("circularity"),
            "mean_elevation_m": props.get("mean_elevation_m"),
            "distance_to_water_m": val_res.distance_to_water_m,
            "centroid_wgs84": centroid_wgs,
            "crs_epsg": f"EPSG:{target_epsg}",
            "composite_image_path": str(composite_path),
            "vlm_verdict": vlm_verdict,
        }
        if looting_alert:
            report_payload["patrimonial_priority"] = looting_alert["alert"]
            report_payload["nearest_known_site"] = looting_alert["nearest_known_site"]
            report_payload["diameter_m"] = looting_alert["diameter_m"]
            report_payload["looting_osm_context"] = looting_alert["osm_historic_context"]
            report_payload["looting_ign_context"] = looting_alert["ign_settlement_context"]

        dossier_path = generate_inapl_dossier(report_payload, out_dir=settings.reports_dir)

        candidates_summary.append({
            "candidate_id": cand_id,
            "type": props.get("anomaly_type"),
            "classification": val_res.classification,
            "confidence": props.get("confidence"),
            "ml_probability": ml_prob,
            "patrimonial_priority": looting_alert["alert"] if looting_alert else None,
            "vlm_verdict": vlm_verdict.get("verdict"),
            "area_m2": props.get("area_m2"),
            "distance_to_water_m": val_res.distance_to_water_m,
            "composite_image": str(composite_path),
            "dossier_path": dossier_path,
        })

    return {
        "status": "success",
        "input_source": str(src_file),
        "dtm_path": dtm_path,
        "slrm_path": relief_res.slrm_path,
        "slope_path": relief_res.slope_path,
        "crs_epsg": target_epsg,
        "total_anomalies_detected": len(features),
        "candidates": candidates_summary,
        "confidential_annex_path": str(settings.reports_dir / "ANEXO_CONFIDENCIAL_COORDENADAS.json"),
    }


@mcp.tool()
def tool_fetch_elevation_tile(target_zone: str = "ZONA_1_TASTIL") -> str:
    """Descarga y reproyecta automáticamente a POSGAR 2007 un tile real de elevación (Copernicus DEM GLO-30).

    Zonas preconfiguradas en el Noroeste Argentino (NOA):
    - `ZONA_1_TASTIL`: Santa Rosa de Tastil / Quebrada del Toro (Salta, EPSG:5345).
    - `ZONA_2_YOCAVIL`: Valle de Yocavil / Santa María / Quilmes (Catamarca / Tucumán, EPSG:5345).
    - `ZONA_3_TINOGASTA`: Región de Tinogasta / Fiambalá / Watungasta (Catamarca, EPSG:5344).

    Args:
        target_zone: Identificador de la zona objetivo.

    Returns:
        Ruta como string al archivo GeoTIFF validado y proyectado en POSGAR 2007.
    """
    from src.core.data_fetcher import fetch_elevation_tile

    settings.ensure_directories()
    return fetch_elevation_tile(target_zone=target_zone, cache_dir=settings.data_dir)


@mcp.tool()
async def tool_autonomous_prospect(
    target_zone: str = "ZONA_1_TASTIL",
    window_size_m: float = 500.0,
    overlap_ratio: float = 0.15,
    max_candidates_to_validate: int = 12,
    ml_mode: str = "advisory",
    dem_provider: str = "auto",
    optical_provider: str | None = None,
    hunt_highres: bool = False,
    highres_id: str | None = None,
) -> dict:
    """Ejecuta el scanner de prospección arqueológica 100% autónomo (Zero Human-in-the-Loop).

    Descarga recortes reales DEM según proveedor/bioma (Copernicus AWS, FABDEM, Planetary STAC,
    IGN WCS) o datasets UAV/LiDAR de alta resolución, subdivide en celdas de 500x500 m,
    detecta relieve positivo y negativo, valida contra IGN/OSM/sitios conocidos, obtiene contexto
    óptico/multiespectral (Sentinel-2 NDVI/NDWI + chip RGB) para candidatos inéditos, renderiza
    láminas de 4 o 6 paneles y genera dossiers INAPL (Ley 25.743).
    """
    from src.autonomous_prospector import run_autonomous_prospector

    return await run_autonomous_prospector(
        target_zone=target_zone,
        window_size_m=window_size_m,
        overlap_ratio=overlap_ratio,
        max_candidates_to_validate=max_candidates_to_validate,
        ml_mode=ml_mode,
        dem_provider=dem_provider,
        optical_provider=optical_provider,
        hunt_highres=hunt_highres,
        highres_id=highres_id,
    )


@mcp.tool()
def tool_vlm_judge_candidate(candidate_id: str) -> dict:
    """Prepara la evaluación pericial multimodal de un candidato para el agente anfitrión.

    Devuelve la ruta de la lámina compuesta (Hillshade 1.5x + SLRM + Perfil 2D), el prompt pericial de
    Arqueólogo Espacial Senior (CONICET, NOA), las métricas del candidato y el JSON Schema `VLMVerdict`.
    El agente debe inspeccionar la imagen y registrar su dictamen con `tool_record_vlm_verdict`.

    Args:
        candidate_id: Identificador del candidato (ej. 'ARQ-0001').
    """
    from src.core.vlm_judge import prepare_mcp_judgement

    return prepare_mcp_judgement(candidate_id)


@mcp.tool()
def tool_record_vlm_verdict(candidate_id: str, verdict_json: dict) -> dict:
    """Registra el dictamen pericial `VLMVerdict` de un candidato.

    Valida el esquema, lo cachea, regenera el dossier INAPL con la sección 5 (Juicio Pericial IA
    Multimodal) y, si el veredicto es NATURAL o ARTEFACTO, quita el candidato de
    `MAPA_FINAL_PROSPECCION.geojson` y lo archiva en `DESCARTES_VLM.json`.

    Args:
        candidate_id: Identificador del candidato.
        verdict_json: Objeto con verdict, certainty_pct, functional_interpretation,
            geomorphological_justification, field_inspection_recommended y backend.
    """
    from src.core.vlm_judge import record_vlm_verdict

    return record_vlm_verdict(candidate_id, verdict_json)


@mcp.tool()
async def tool_hunt_highres_lidar_argentina(
    bbox: list[float] = [-69.5, -30.0, -64.5, -22.0],
) -> str:
    """Busca autónomamente datasets LiDAR y fotogramétricos de alta resolución (0.15 m a 5 m) en Argentina y Andes Centrales.

    Consulta en tiempo real:
    1. OpenTopography Catalog API (`portal.opentopography.org/API/otCatalog`, incluyendo catálogos federados).
    2. Zenodo Scientific Repository API (`zenodo.org/api/records`) filtrando GeoTIFFs sub-métricos y nubes LiDAR (.las/.laz) de vuelos científicos UAV/TLS en los Andes argentinos.
    3. Catálogo WCS/WMS del Instituto Geográfico Nacional (IGN Argentina, `wms.ign.gob.ar/geoserver/ows`).

    Args:
        bbox: Bounding box `[minx, miny, maxx, maxy]` en grados WGS84 (por defecto NOA/Andes: `[-69.5, -30.0, -64.5, -22.0]`).

    Returns:
        JSON formateado con el resumen por fuente, la lista priorizada de datasets de alta resolución encontrados, su resolución en metros y sus URLs directas de descarga.
    """
    import json
    from src.core.highres_hunter import HighResLidarHunter

    hunter = HighResLidarHunter()
    result = await hunter.hunt_all_sources(bbox=bbox)
    return json.dumps(result, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    mcp.run()
