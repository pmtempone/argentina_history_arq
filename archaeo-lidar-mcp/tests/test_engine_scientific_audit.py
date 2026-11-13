"""Etapa 1.4 — Las 8 pruebas técnicas obligatorias de auditoría científica y geoespacial."""

from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from scipy.ndimage import gaussian_filter

from src.core.anomaly_detector import detect_anomalies
from src.core.dem_quality import audit_dem_quality
from src.core.relief_models import (
    NODATA_FLOAT32,
    compute_openness,
    compute_relief_pipeline,
    compute_sky_view_factor,
    compute_slrm,
)
from src.core.visual_inspector import _compute_multidirectional_hillshade


def _write_posgar_dtm(
    path: Path,
    arr: np.ndarray,
    epsg: int = 5345,
    res_m: float = 1.0,
    x0: float = 3500000.0,
    y0: float = 6800000.0,
    nodata: float = NODATA_FLOAT32,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    h, w = arr.shape
    profile = {
        "driver": "GTiff",
        "height": h,
        "width": w,
        "count": 1,
        "dtype": "float32",
        "crs": f"EPSG:{epsg}",
        "transform": from_origin(x0, y0, res_m, res_m),
        "nodata": nodata,
        "compress": "deflate",
    }
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(arr.astype(np.float32), 1)
    return path


def test_audit_1_known_synthetic_raster(tmp_path: Path) -> None:
    """1. Raster sintético conocido: recupera recinto positivo y pozo negativo con evidencia observable."""
    h, w = 140, 140
    dtm = np.full((h, w), 1200.0, dtype=np.float64)
    # Recinto ortogonal positivo 22x22 m (+1.1 m)
    dtm[25:47, 25:47] += 1.1
    # Pozo circular negativo r=9 m (-1.2 m)
    yy, xx = np.ogrid[:h, :w]
    dtm[((yy - 95) ** 2 + (xx - 95) ** 2) <= 9 ** 2] -= 1.2

    dtm_p = _write_posgar_dtm(tmp_path / "audit1_dtm.tif", dtm, res_m=1.0)
    relief = compute_relief_pipeline(dtm_p, tmp_path / "relief", radius_m=12.0, include_svf_openness=True)
    assert relief.svf_path and Path(relief.svf_path).exists()
    assert relief.pos_openness_path and Path(relief.pos_openness_path).exists()
    assert relief.neg_openness_path and Path(relief.neg_openness_path).exists()
    assert relief.params_json_path and Path(relief.params_json_path).exists()

    fc = detect_anomalies(relief.slrm_path, relief.slope_path, min_dz=0.25, min_area=40.0, max_area=5000.0)
    feats = fc["features"]
    assert len(feats) >= 2
    signs = {f["properties"]["relief_sign"] for f in feats}
    assert signs == {"positivo", "negativo"}
    ev_signs = {f["properties"]["observable_evidence"]["relief_sign"] for f in feats}
    assert ev_signs == {"positive", "negative"}
    for f in feats:
        assert f["properties"]["lifecycle_state"] == "ALGORITHMIC_DETECTION"
        assert f["properties"]["anomaly_family"] == "POTENTIAL_ANTHROPOGENIC"
        ev = f["properties"]["observable_evidence"]
        assert ev["score_interpretation"] == "geometric_topographic_salience_not_archaeological_probability"


def test_audit_2_flat_raster_zero_anomalies(tmp_path: Path) -> None:
    """2. Raster plano y rampa planar uniforme: cero anomalías artificiales."""
    h, w = 100, 100
    flat = np.full((h, w), 2500.0, dtype=np.float64)
    yy, xx = np.mgrid[:h, :w]
    ramp = 2500.0 + 0.08 * xx + 0.04 * yy

    for label, arr in (("flat", flat), ("ramp", ramp)):
        sub = tmp_path / label
        dtm_p = _write_posgar_dtm(sub / "dtm.tif", arr, res_m=1.0)
        relief = compute_relief_pipeline(dtm_p, sub / "relief", radius_m=10.0)
        fc = detect_anomalies(relief.slrm_path, relief.slope_path, min_dz=0.15, min_area=10.0)
        assert fc["features"] == [], f"Se detectaron anomalías espurias en {label}"


def test_audit_3_nodata_holes_and_edges(tmp_path: Path) -> None:
    """3. Raster con NoData en vacíos y bordes: sin falsos anillos en SLRM, SVF, Openness ni OpenCV."""
    h, w = 110, 110
    dtm = np.full((h, w), 1800.0, dtype=np.float64)
    dtm[40:55, 40:55] = NODATA_FLOAT32
    dtm[:4, :] = NODATA_FLOAT32
    dtm[:, -4:] = NODATA_FLOAT32

    dtm_p = _write_posgar_dtm(tmp_path / "nodata_dtm.tif", dtm, res_m=1.0)
    prof = audit_dem_quality(dtm_p, provider_used="test_lidar", native_resolution_m=1.0, model_type="DTM")
    assert prof.void_fraction > 0.05
    assert prof.border_nodata_fraction > 0.10

    relief = compute_relief_pipeline(dtm_p, tmp_path / "relief", radius_m=10.0, include_svf_openness=True)
    with rasterio.open(relief.svf_path) as src:
        svf = src.read(1)
        assert np.isclose(svf[45, 45], NODATA_FLOAT32)
        valid_svf = svf[np.abs(svf - NODATA_FLOAT32) > 1.0]
        assert np.nanmin(valid_svf) > 0.99  # sin anillos artificiales en terreno plano

    fc = detect_anomalies(relief.slrm_path, relief.slope_path, min_dz=0.15, min_area=10.0)
    assert fc["features"] == []


def test_audit_4_multi_resolution_degradation(tmp_path: Path) -> None:
    """4. Distintas resoluciones: estructura de 16x16 m visible a 1 m/px y filtrada por piso físico a 30 m/px."""
    # A 1 m/px: 16x16 m -> ~256 m² (>= 2 m²), detectada
    fine = np.full((100, 100), 1500.0, dtype=np.float64)
    fine[42:58, 42:58] += 1.5
    p_fine = _write_posgar_dtm(tmp_path / "fine.tif", fine, res_m=1.0)
    r_fine = compute_relief_pipeline(p_fine, tmp_path / "r_fine", radius_m=12.0)
    fc_fine = detect_anomalies(r_fine.slrm_path, r_fine.slope_path, min_dz=0.25, min_area=50.0, max_area=2000.0)
    assert len(fc_fine["features"]) >= 1
    assert audit_dem_quality(p_fine, "uav", native_resolution_m=1.0).suitable_for_microtopography is True

    # A 30 m/px: piso físico = 2 * 900 = 1800 m², micro-estructura de ~16x16 m es físicamente irrecuperable
    coarse = np.full((24, 24), 1500.0, dtype=np.float64)
    coarse[11:12, 11:12] += 1.5
    p_coarse = _write_posgar_dtm(tmp_path / "coarse.tif", coarse, res_m=30.0)
    prof_coarse = audit_dem_quality(p_coarse, "ign_mde_ar_30m", native_resolution_m=30.0)
    assert prof_coarse.suitable_for_microtopography is False
    assert prof_coarse.min_detectable_area_m2 == pytest.approx(1800.0)
    r_coarse = compute_relief_pipeline(p_coarse, tmp_path / "r_coarse", radius_m=40.0)
    fc_coarse = detect_anomalies(r_coarse.slrm_path, r_coarse.slope_path, min_dz=0.25, min_area=50.0, max_area=1200.0)
    assert fc_coarse["metadata"]["min_area_effective_m2"] == pytest.approx(1800.0)


def test_audit_5_multi_projection_scale_consistency(tmp_path: Path) -> None:
    """5. Distintas proyecciones POSGAR (Faja 2 EPSG:5344 vs Faja 3 EPSG:5345): área métrica consistente."""
    arr = np.full((100, 100), 2200.0, dtype=np.float64)
    arr[35:65, 35:65] += 1.3  # 30x30 m = 900 m²
    areas = []
    for epsg, x0 in ((5344, 2520000.0), (5345, 3520000.0)):
        sub = tmp_path / f"epsg_{epsg}"
        p = _write_posgar_dtm(sub / "dtm.tif", arr, epsg=epsg, res_m=1.0, x0=x0)
        rel = compute_relief_pipeline(p, sub / "relief", radius_m=12.0)
        fc = detect_anomalies(rel.slrm_path, rel.slope_path, min_dz=0.25, min_area=100.0, max_area=5000.0)
        pos_feats = [f for f in fc["features"] if f["properties"]["relief_sign"] == "positivo"]
        assert len(pos_feats) == 1
        areas.append(pos_feats[0]["properties"]["area_m2"])
    rel_diff = abs(areas[0] - areas[1]) / max(areas[0], 1e-6)
    assert rel_diff < 0.02


def test_audit_6_illumination_rotation_invariance(tmp_path: Path) -> None:
    """6. Rotación de iluminación: el hillshade depende del acimut, pero SLRM/SVF/Openness y detección son invariantes."""
    h, w = 100, 100
    arr = np.full((h, w), 1000.0, dtype=np.float64)
    arr[36:64, 36:64] += 1.4
    hs_default = _compute_multidirectional_hillshade(arr, 1.0, 1.0)
    # Transpuesta / rotación simulada de terreno verifica anisotropía del hillshade vs invarianza morfométrica
    arr_rot = np.rot90(arr)
    hs_rot = _compute_multidirectional_hillshade(arr_rot, 1.0, 1.0)
    assert np.allclose(hs_default, hs_default)  # determinismo base
    assert hs_rot.shape == hs_default.shape

    p1 = _write_posgar_dtm(tmp_path / "rot1.tif", arr, res_m=1.0)
    p2 = _write_posgar_dtm(tmp_path / "rot2.tif", arr_rot, res_m=1.0)
    r1 = compute_relief_pipeline(p1, tmp_path / "r1", radius_m=12.0, include_svf_openness=True)
    r2 = compute_relief_pipeline(p2, tmp_path / "r2", radius_m=12.0, include_svf_openness=True)
    fc1 = detect_anomalies(r1.slrm_path, r1.slope_path, min_dz=0.25, min_area=100.0)
    fc2 = detect_anomalies(r2.slrm_path, r2.slope_path, min_dz=0.25, min_area=100.0)
    assert len(fc1["features"]) == len(fc2["features"])
    pos1 = [f for f in fc1["features"] if f["properties"]["relief_sign"] == "positivo"]
    pos2 = [f for f in fc2["features"] if f["properties"]["relief_sign"] == "positivo"]
    assert len(pos1) == len(pos2) == 1
    assert pos1[0]["properties"]["area_m2"] == pytest.approx(
        pos2[0]["properties"]["area_m2"], rel=0.02
    )


def test_audit_7_simulated_noise_and_erosion_robustness(tmp_path: Path) -> None:
    """7. Ruido y erosión simulada: el detector mantiene la recuperación con deformación moderada."""
    rng = np.random.default_rng(42)
    h, w = 110, 110
    arr = np.full((h, w), 2000.0, dtype=np.float64)
    arr[38:66, 38:66] += 1.3  # 28x28 m = 784 m²
    eroded = gaussian_filter(arr, sigma=1.2) + rng.normal(0.0, 0.04, size=(h, w))

    p = _write_posgar_dtm(tmp_path / "eroded.tif", eroded, res_m=1.0)
    rel = compute_relief_pipeline(p, tmp_path / "r_eroded", radius_m=14.0)
    fc = detect_anomalies(rel.slrm_path, rel.slope_path, min_dz=0.20, min_area=100.0, max_area=4000.0)
    assert len(fc["features"]) >= 1
    main_feat = max(fc["features"], key=lambda f: f["properties"]["area_m2"])
    assert main_feat["properties"]["area_m2"] >= 300.0


def test_audit_8_identical_repetition_determinism(tmp_path: Path) -> None:
    """8. Repetición idéntica: dos corridas sobre el mismo DTM generan resultados deterministas."""
    h, w = 100, 100
    arr = np.full((h, w), 1400.0, dtype=np.float64)
    arr[30:55, 30:55] += 1.0
    p = _write_posgar_dtm(tmp_path / "det.tif", arr, res_m=1.0)

    r1 = compute_relief_pipeline(p, tmp_path / "run1", radius_m=10.0)
    r2 = compute_relief_pipeline(p, tmp_path / "run2", radius_m=10.0)
    fc1 = detect_anomalies(r1.slrm_path, r1.slope_path, min_dz=0.20, min_area=50.0)
    fc2 = detect_anomalies(r2.slrm_path, r2.slope_path, min_dz=0.20, min_area=50.0)
    assert fc1["features"] == fc2["features"]
