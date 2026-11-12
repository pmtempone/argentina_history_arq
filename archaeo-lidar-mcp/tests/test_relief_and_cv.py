"""Tests unitarios y de integración para modelos de relieve (SLRM/Slope), OpenCV y láminas visuales."""

import json
import math
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from src.core.anomaly_detector import detect_anomalies
from src.core.crs_manager import ensure_metric_crs, get_posgar_faja, reproject_geometry
from src.core.relief_models import compute_slrm, compute_slope
from src.core.report_generator import generate_inapl_dossier
from src.core.visual_inspector import (
    render_candidate_composite,
    render_pointcloud_cross_section,
)


def test_posgar_faja_detection() -> None:
    """Verifica la asignación exacta de fajas POSGAR 2007 (EPSG:5343 a EPSG:5349) según longitud."""
    assert get_posgar_faja(-71.2) == 5343  # Faja 1
    assert get_posgar_faja(-68.5) == 5344  # Faja 2 (NOA Oeste / Cuyo)
    assert get_posgar_faja(-65.4) == 5345  # Faja 3 (Quebrada de Humahuaca / Valles Calchaquíes)
    assert get_posgar_faja(-63.0) == 5346  # Faja 4
    assert get_posgar_faja(-59.5) == 5347  # Faja 5
    assert get_posgar_faja(-57.0) == 5348  # Faja 6
    assert get_posgar_faja(-54.2) == 5349  # Faja 7


def test_slrm_slope_and_cv_anomaly_detection(synthetic_posgar_dtm: Path, tmp_path: Path) -> None:
    """Verifica que compute_slrm, compute_slope y detect_anomalies detecten la pirca y el chenque inyectados."""
    slrm_path = tmp_path / "slrm.tif"
    slope_path = tmp_path / "slope.tif"

    out_slrm = compute_slrm(synthetic_posgar_dtm, slrm_path, radius_m=15.0)
    out_slope = compute_slope(synthetic_posgar_dtm, slope_path)

    assert Path(out_slrm).exists()
    assert Path(out_slope).exists()

    with rasterio.open(out_slrm) as src_slrm:
        assert src_slrm.crs.to_epsg() == 5344
        assert src_slrm.dtypes[0] == "float32"

    fc = detect_anomalies(out_slrm, out_slope, min_area=12.0, max_area=6000.0)
    assert fc["type"] == "FeatureCollection"
    features = fc["features"]

    # Deben detectarse exactamente las dos estructuras inyectadas
    assert len(features) == 2

    types_found = {f["properties"]["anomaly_type"] for f in features}
    assert "recinto_ortogonal" in types_found
    assert "estructura_circular" in types_found

    # Verificar áreas con margen de error < 15%
    expected_rect_area = 14.0 * 8.0  # 112.0 m²
    expected_circ_area = math.pi * (5.0**2)  # ~78.54 m²

    for feat in features:
        props = feat["properties"]
        area_m2 = float(props["area_m2"])
        if props["anomaly_type"] == "recinto_ortogonal":
            rel_err_rect = abs(area_m2 - expected_rect_area) / expected_rect_area
            assert rel_err_rect < 0.15, f"Error de área en recinto ({area_m2} vs {expected_rect_area}): {rel_err_rect:.2%}"
        elif props["anomaly_type"] == "estructura_circular":
            rel_err_circ = abs(area_m2 - expected_circ_area) / expected_circ_area
            assert rel_err_circ < 0.15, f"Error de área en círculo ({area_m2} vs {expected_circ_area}): {rel_err_circ:.2%}"

        # Verificar que las coordenadas finales en GeoJSON estén en WGS84 (Argentina: lon [-75, -53], lat [-56, -21])
        lon, lat = props["centroid_wgs84"]
        assert -75.0 <= lon <= -53.0
        assert -56.0 <= lat <= -21.0

        geom = feat["geometry"]
        assert geom["type"] == "Polygon"
        ring = geom["coordinates"][0]
        assert len(ring) >= 4
        for vx, vy in ring:
            assert -75.0 <= vx <= -53.0
            assert -56.0 <= vy <= -21.0

        # Como están a ~74 m (< 80 m), ambos deben haberse agrupado en un complejo arquitectónico
        assert props["is_architectural_complex"] is True
        assert props["complex_group_type"] == "complejo_agrupado"


def test_negative_relief_detection(synthetic_posgar_dtm_with_pit: Path, tmp_path: Path) -> None:
    """Verifica que el detector encuentre el hundimiento plantado (casa-pozo) además de las positivas.

    El DTM sintético tiene una pirca (+0.6 m), un chenque circular (+0.6 m) y un pozo de
    12 m de diámetro excavado a -0.6 m. El pase de relieve negativo debe recuperar el pozo
    con `estructura_hundida`, valor SLRM con signo negativo y fuera del complejo (< 80 m).
    """
    slrm_path = compute_slrm(synthetic_posgar_dtm_with_pit, tmp_path / "slrm_neg.tif", radius_m=15.0)
    slope_path = compute_slope(synthetic_posgar_dtm_with_pit, tmp_path / "slope_neg.tif")

    fc = detect_anomalies(slrm_path, slope_path, min_area=12.0, max_area=6000.0)
    features = fc["features"]
    types_found = {f["properties"]["anomaly_type"] for f in features}

    assert "estructura_hundida" in types_found
    # Las estructuras positivas siguen detectándose
    assert "recinto_ortogonal" in types_found
    assert "estructura_circular" in types_found

    pits = [f for f in features if f["properties"]["anomaly_type"] == "estructura_hundida"]
    assert len(pits) == 1

    pit = pits[0]
    props = pit["properties"]
    # El hundimiento debe reportar desviación SLRM negativa
    assert props["mean_elevation_m"] < 0.0
    assert props["relief_sign"] == "negativo"
    # Área teórica del pozo: pi * 6^2 ≈ 113.10 m² (tolerancia 15%)
    expected_area = math.pi * (6.0**2)
    rel_err = abs(float(props["area_m2"]) - expected_area) / expected_area
    assert rel_err < 0.15, f"Error de área en pozo ({props['area_m2']} vs {expected_area}): {rel_err:.2%}"
    # A más de 80 m de la pirca/chenque: no debe agruparse en el complejo
    assert props["is_architectural_complex"] is False
    # Geometría en WGS84 válida (Argentina)
    lon, lat = props["centroid_wgs84"]
    assert -75.0 <= lon <= -53.0
    assert -56.0 <= lat <= -21.0


def test_min_area_physical_floor_by_resolution(tmp_path: Path) -> None:
    """Verifica el piso físico de área: `min_area` no puede quedar por debajo de 2 píxeles del raster.

    Con un raster de 10 m/px (píxel = 100 m²), un `min_area` solicitado de 12 m² es
    físicamente irrecuperable; el detector debe elevarlo a 200 m² y registrar la
    aplicación del piso en los metadatos.
    """
    width = height = 40
    res = 10.0
    transform = from_origin(2500000.0, 7000200.0, res, res)
    data = np.full((height, width), 2000.0, dtype=np.float32)

    coarse_dtm = tmp_path / "coarse_dtm.tif"
    profile = {
        "driver": "GTiff",
        "height": height,
        "width": width,
        "count": 1,
        "dtype": "float32",
        "crs": rasterio.crs.CRS.from_epsg(5344),
        "transform": transform,
        "nodata": -9999.0,
    }
    with rasterio.open(coarse_dtm, "w", **profile) as dst:
        dst.write(data, 1)

    slrm_path = compute_slrm(coarse_dtm, tmp_path / "coarse_slrm.tif", radius_m=25.0)
    slope_path = compute_slope(coarse_dtm, tmp_path / "coarse_slope.tif")

    fc = detect_anomalies(slrm_path, slope_path, min_area=12.0, max_area=6000.0)
    meta = fc["metadata"]

    assert meta["pixel_area_m2"] == pytest.approx(100.0)
    assert meta["min_area_requested_m2"] == pytest.approx(12.0)
    assert meta["min_area_effective_m2"] == pytest.approx(200.0)
    assert meta["min_area_floor_applied"] is True
    # Terreno plano sin estructuras: sin detecciones
    assert len(fc["features"]) == 0


def test_detection_recall_at_satellite_resolution(tmp_path: Path) -> None:
    """Mide el recall del detector a resolución satelital (30 m/px, Copernicus GLO-30).

    Planta estructuras del tamaño mínimo realista detectable a 30 m/px (≈ 2+ píxeles:
    una plaza/kancha de 150x90 m y un corral circular de radio 105 m) y verifica que
    ambas se detecten con tipología y ubicación correctas. A esta resolución el área
    se sobreestima por la corrección de medio píxel, así que la tolerancia es amplia.
    """
    width = height = 64
    res = 30.0
    transform = from_origin(2500000.0, 7000200.0, res, res)

    cols = (np.arange(width, dtype=np.float64) + 0.5) * res
    rows = (np.arange(height, dtype=np.float64) + 0.5) * res
    xx, yy = np.meshgrid(cols, rows)

    # Terreno base suave de larga longitudelada: amplitud baja para que el residual SLRM
    # propio del terreno (~6% de la amplitud tras el filtro gaussiano) quede muy por debajo
    # del umbral min_dz de 0.15 m y no compita con las estructuras plantadas.
    z = 2000.0 + 1.0 * np.sin(xx / 300.0) + 1.0 * np.cos(yy / 300.0)

    # 1. Plaza / kancha rectangular 150x90 m (+0.6 m) centrada en (720, 720) m locales
    rect_mask = (np.abs(xx - 720.0) <= 75.0) & (np.abs(yy - 720.0) <= 45.0)
    z[rect_mask] += 0.60

    # 2. Corral circular radio 105 m (3.5 px) (+0.6 m) centrado en (1200, 840) m locales.
    #    A 30 m/px un círculo de radio < ~3 px rasteriza como un cuadrado perfecto
    #    (rectangularidad ~0.94) y es indistinguible de un recinto ortogonal. La separación
    #    con el rectángulo es de 10 px: la clausura morfológica 3x3 cierra huecos de hasta 2 px.
    z[np.hypot(xx - 1200.0, yy - 840.0) <= 105.0] += 0.60

    coarse_dtm = tmp_path / "glo30_planted_dtm.tif"
    profile = {
        "driver": "GTiff",
        "height": height,
        "width": width,
        "count": 1,
        "dtype": "float32",
        "crs": rasterio.crs.CRS.from_epsg(5344),
        "transform": transform,
        "nodata": -9999.0,
    }
    with rasterio.open(coarse_dtm, "w", **profile) as dst:
        dst.write(z.astype(np.float32), 1)

    # Radio de tendencia SLRM > tamaño de la estructura en píxeles: a 30 m/px, 240 m = 8 px,
    # suficiente para que el interior de la estructura (2.5-5 px) quede elevado respecto a la
    # tendencia. Con radios ~1 px el SLRM solo marca los bordes y la detección colapsa.
    slrm_path = compute_slrm(coarse_dtm, tmp_path / "glo30_slrm.tif", radius_m=240.0)
    slope_path = compute_slope(coarse_dtm, tmp_path / "glo30_slope.tif")

    # Margen de borde: la tendencia SLRM está sesgada cerca del borde del raster (modo 'nearest'
    # del filtro gaussiano genera residual espurio de hasta ±0.25 m en terreno colinar) y los
    # tiles satelitales son chicos en píxeles (500 m = ~16 px a 30 m/px). El overlap del tiling
    # garantiza que una estructura cerca de un borde se detecte desde la celda vecina.
    fc = detect_anomalies(
        slrm_path,
        slope_path,
        min_area=12.0,
        max_area=60000.0,
        border_margin_px=12,
    )
    features = fc["features"]
    types_found = {f["properties"]["anomaly_type"] for f in features}

    # Recall: las dos estructuras plantadas deben detectarse
    assert len(features) == 2, f"Se esperaban 2 detecciones, hubo {len(features)}: {types_found}"
    assert "recinto_ortogonal" in types_found
    assert "estructura_circular" in types_found

    # Piso físico de área aplicado: 2 px x (30 m)^2 = 1800 m²
    meta = fc["metadata"]
    assert meta["min_area_floor_applied"] is True
    assert meta["min_area_effective_m2"] == pytest.approx(1800.0)

    # Centroides dentro de la estructura plantada (±90 m) y en WGS84 válido
    # Local: x hacia el Este desde west=2500000; y hacia el Sur desde north=7000200.
    expected_centroids = {
        "recinto_ortogonal": (2500000.0 + 720.0, 7000200.0 - 720.0),
        "estructura_circular": (2500000.0 + 1200.0, 7000200.0 - 840.0),
    }
    for feat in features:
        props = feat["properties"]
        exp = expected_centroids[props["anomaly_type"]]
        lon, lat = props["centroid_wgs84"]
        assert -75.0 <= lon <= -53.0
        assert -56.0 <= lat <= -21.0
        # Distancia métrica centroide detectado vs plantado (reproyectando a la faja)
        from pyproj import CRS, Transformer

        to_metric = Transformer.from_crs(CRS.from_epsg(4326), CRS.from_epsg(5344), always_xy=True)
        cx, cy = to_metric.transform(lon, lat)
        dist_planted = math.hypot(cx - exp[0], cy - exp[1])
        assert dist_planted < 90.0, (
            f"Centroide lejos de la estructura plantada: {props['anomaly_type']} "
            f"({cx:.0f}, {cy:.0f}) vs ({exp[0]:.0f}, {exp[1]:.0f})"
        )

    # Área sobreestimada a resolución gruesa (corrección de medio píxel) pero del orden correcto
    for feat in features:
        area_m2 = float(feat["properties"]["area_m2"])
        if feat["properties"]["anomaly_type"] == "recinto_ortogonal":
            assert 12000.0 <= area_m2 <= 25000.0, f"Área recinto fuera de rango: {area_m2}"
        else:
            assert 25000.0 <= area_m2 <= 50000.0, f"Área círculo fuera de rango: {area_m2}"


def test_visual_inspector_and_dossier(synthetic_posgar_dtm: Path, tmp_path: Path) -> None:
    """Verifica la generación de la lámina de 3 paneles, el corte transversal de nube y el dossier INAPL."""
    slrm_path = compute_slrm(synthetic_posgar_dtm, tmp_path / "slrm_vis.tif", radius_m=15.0)
    composite_png = tmp_path / "composite.png"

    bbox_posgar = [2500040.0, 7000040.0, 2500150.0, 7000160.0]
    out_png = render_candidate_composite(
        dtm_path=synthetic_posgar_dtm,
        slrm_path=slrm_path,
        bbox_posgar=bbox_posgar,
        out_png_path=composite_png,
    )
    assert Path(out_png).exists()
    assert Path(out_png).stat().st_size > 1000

    # Crear nube sintética .npz con retornos ASPRS Clase 2 (suelo) y Clases 3-5 (vegetación)
    rng = np.random.default_rng(42)
    n_ground = 400
    n_veg = 150
    gx = rng.uniform(2500050.0, 2500080.0, n_ground)
    gy = rng.uniform(7000130.0, 7000140.0, n_ground)
    gz = 2000.0 + 0.6 * ((gx >= 2500058.0) & (gx <= 2500072.0)).astype(np.float64)
    gcls = np.full(n_ground, 2, dtype=np.int32)

    vx = rng.uniform(2500050.0, 2500080.0, n_veg)
    vy = rng.uniform(7000130.0, 7000140.0, n_veg)
    vz = 2001.5 + rng.uniform(0.2, 2.5, n_veg)
    vcls = rng.choice([3, 4, 5], size=n_veg).astype(np.int32)

    cloud_npz = tmp_path / "synthetic_cloud.npz"
    np.savez(
        cloud_npz,
        X=np.concatenate([gx, vx]),
        Y=np.concatenate([gy, vy]),
        Z=np.concatenate([gz, vz]),
        Classification=np.concatenate([gcls, vcls]),
    )

    cs_res = render_pointcloud_cross_section(
        las_path=cloud_npz,
        p1_xy=[2500050.0, 7000135.0],
        p2_xy=[2500080.0, 7000135.0],
        swath_width_m=2.0,
        out_png_path=tmp_path / "cross_section.png",
    )
    assert Path(cs_res.plot_image_path).exists()
    assert cs_res.ground_points_count > 0
    assert cs_res.vegetation_points_count > 0
    assert cs_res.ground_density_pts_m2 > 0.0
    assert 0.0 < cs_res.profile_integrity_score <= 1.0

    # Verificar generación de dossier INAPL y separación de coordenadas confidenciales
    dossier_dir = tmp_path / "reports"
    dossier_md_path = generate_inapl_dossier(
        candidate_data={
            "id": "ARQ-0001",
            "anomaly_type": "recinto_ortogonal",
            "classification": "CANDIDATO_INEDITO",
            "confidence": 0.94,
            "area_m2": 112.0,
            "rectangularity": 0.92,
            "circularity": 0.65,
            "mean_elevation_m": 0.58,
            "distance_to_water_m": None,  # Sin datos IGN
            "centroid_wgs84": [-69.123456, -27.123456],
            "geometry_geojson": {"type": "Point", "coordinates": [-69.123456, -27.123456]},
        },
        out_dir=dossier_dir,
    )
    md_text = Path(dossier_md_path).read_text(encoding="utf-8")
    assert "No determinado (sin datos IGN)" in md_text
    annex_file = dossier_dir / "ANEXO_CONFIDENCIAL_COORDENADAS.json"
    assert annex_file.exists()
    # Las coordenadas sensibles NO deben figurar en el Markdown público pero SÍ en el JSON confidencial
    assert "-69.123456" not in md_text
    annex_data = json.loads(annex_file.read_text(encoding="utf-8"))
    assert annex_data["centroid_wgs84"] == [-69.123456, -27.123456]

    # Probar lámina con centroide explícito del candidato
    centroid_png = tmp_path / "composite_centroid.png"
    out_cent = render_candidate_composite(
        dtm_path=synthetic_posgar_dtm,
        slrm_path=slrm_path,
        bbox_posgar=[2500055.0, 7000055.0, 2500075.0, 7000075.0],
        out_png_path=centroid_png,
        centroid_posgar=[2500065.0, 7000065.0],
        buffer_m=15.0,
    )
    assert Path(out_cent).exists()
    assert Path(out_cent).stat().st_size > 1000


def test_reproject_geographic_raster_to_posgar(tmp_path: Path) -> None:
    """Verifica que ensure_metric_crs reproyecte automáticamente un raster en EPSG:4326 a POSGAR 2007."""
    from rasterio.transform import from_origin

    wgs_tif = tmp_path / "input_wgs84.tif"
    # Coordenadas en Quebrada de Humahuaca (Jujuy, ~ -65.35° lon, -23.58° lat -> Faja 3 EPSG:5345)
    transform = from_origin(-65.36, -23.57, 0.0001, 0.0001)
    data = np.full((50, 50), 2500.0, dtype=np.float32)

    with rasterio.open(
        wgs_tif,
        "w",
        driver="GTiff",
        height=50,
        width=50,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=transform,
        nodata=-9999.0,
    ) as dst:
        dst.write(data, 1)

    out_metric_tif = tmp_path / "output_posgar.tif"
    result_path = ensure_metric_crs(wgs_tif, out_metric_tif)
    assert Path(result_path).exists()

    with rasterio.open(result_path) as src:
        assert src.crs.to_epsg() == 5345  # POSGAR 2007 Faja 3

    geom_posgar = {"type": "Point", "coordinates": [3565000.0, 7390000.0]}
    geom_wgs = reproject_geometry(geom_posgar, from_crs="EPSG:5345", to_crs="EPSG:4326")
    assert geom_wgs["type"] == "Point"
    assert -67.5 <= geom_wgs["coordinates"][0] <= -64.5


@pytest.mark.asyncio
async def test_unified_full_pipeline(synthetic_posgar_dtm: Path) -> None:
    """Verifica la ejecución de la herramienta unificada tool_run_full_pipeline."""
    from src.server import tool_run_full_pipeline

    res = await tool_run_full_pipeline(
        input_path=str(synthetic_posgar_dtm),
        resolution=0.5,
        radius_m=15.0,
    )
    assert res["status"] == "success"
    assert res["total_anomalies_detected"] == 2
    assert len(res["candidates"]) == 2
    for cand in res["candidates"]:
        assert Path(cand["composite_image"]).exists()
        assert Path(cand["dossier_path"]).exists()
    assert Path(res["confidential_annex_path"]).exists()
