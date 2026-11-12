"""Tests unitarios para la arquitectura multisatélite (DEM router, optical providers, lámina 6 paneles y purga)."""

import json
from pathlib import Path
from typing import Any, Dict

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from src.core import dem_providers
from src.core.data_fetcher import (
    TARGET_ZONES,
    _reproject_and_supersample_to_posgar,
    fetch_elevation_tile,
    resolve_zone_key,
)
from src.core.optical_providers import cap_rgb_chip_size, compute_spectral_indices_and_stats
from src.core.visual_inspector import render_candidate_composite
from src.core.vlm_judge import record_vlm_verdict


def _write_wgs84_dem(path: Path, min_lon: float, min_lat: float, max_lon: float, max_lat: float) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    w, h = 40, 40
    res_lon = (max_lon - min_lon) / w
    res_lat = (max_lat - min_lat) / h
    arr = np.full((h, w), 1200.0, dtype=np.float32)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=h,
        width=w,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(min_lon, max_lat, res_lon, res_lat),
        nodata=-9999.0,
    ) as dst:
        dst.write(arr, 1)
    return path


def test_zone_17_alias_and_preferred_dem_by_biome() -> None:
    """Verifica la unificación de ZONA_17_CHANI y la asignación de preferred_dem por bioma."""
    assert resolve_zone_key("ZONA_17_VOLCAN_CHANI") == "ZONA_17_CHANI"
    assert "ZONA_17_VOLCAN_CHANI" not in TARGET_ZONES
    assert TARGET_ZONES["ZONA_20_VALLE_GRANDE"]["preferred_dem"] == "fabdem"
    assert TARGET_ZONES["ZONA_23_DELTA_PARANA"]["preferred_dem"] == "fabdem"
    assert TARGET_ZONES["ZONA_1_TASTIL"]["preferred_dem"] == "copernicus_aws"


def test_dem_fallback_chain_and_synthetic_isolation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Si todos los proveedores fallan, escribe en *_SYNTHETIC_FALLBACK_* sin contaminar el caché real."""
    cache_dir = tmp_path / "raw"

    def _always_fail(*args: Any, **kwargs: Any) -> Dict[str, Any]:
        raise RuntimeError("Sin red en test")

    monkeypatch.setattr("src.core.data_fetcher.fetch_dem_window", _always_fail)

    res_meta = fetch_elevation_tile(
        target_zone="ZONA_1_TASTIL",
        cache_dir=cache_dir,
        provider="fabdem",
        return_metadata=True,
    )
    assert isinstance(res_meta, dict)
    assert res_meta["is_synthetic_fallback"] is True
    assert "SYNTHETIC_FALLBACK" in Path(res_meta["path"]).name
    assert not (cache_dir / "zona_1_tastil_posgar_5345.tif").exists()

    with rasterio.open(res_meta["path"]) as src:
        assert src.tags().get("SYNTHETIC_FALLBACK") == "TRUE"

    # Cuando vuelve la red: la cadena fabdem -> copernicus_aws resuelve el archivo definitivo real
    def _mock_copernicus(bbox_wgs84, out_path, zone_meta):
        _write_wgs84_dem(out_path, *bbox_wgs84)
        return {
            "path": out_path,
            "provider_used": "copernicus_aws",
            "native_resolution_m": 30.0,
            "is_synthetic_fallback": False,
        }

    monkeypatch.setattr(
        "src.core.data_fetcher.fetch_dem_window",
        dem_providers.fetch_dem_window,
    )
    monkeypatch.setattr(dem_providers, "_fetch_fabdem", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("No GEE")))
    monkeypatch.setattr(dem_providers, "_fetch_ign_wcs", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("No WCS")))
    monkeypatch.setattr(dem_providers, "_fetch_copernicus_aws", _mock_copernicus)

    real_meta = fetch_elevation_tile(
        target_zone="ZONA_1_TASTIL",
        cache_dir=cache_dir,
        provider="fabdem",
        return_metadata=True,
    )
    assert real_meta["is_synthetic_fallback"] is False
    assert real_meta["provider_used"] == "copernicus_aws"
    assert real_meta["native_resolution_m"] == 30.0
    assert (cache_dir / "zona_1_tastil_posgar_5345.tif").exists()


def test_master_side_pixel_cap_and_deflate_compression(tmp_path: Path) -> None:
    """Verifica el tope duro MAX_MASTER_SIDE_PX y compresión deflate."""
    src_tif = _write_wgs84_dem(tmp_path / "src.tif", -65.98, -24.48, -65.94, -24.44)
    dst_tif = tmp_path / "dst_posgar.tif"

    _reproject_and_supersample_to_posgar(
        src_wgs84_path=src_tif,
        dst_posgar_path=dst_tif,
        target_epsg=5345,
        target_resolution_m=1.0,
        max_side_px=256,
    )
    with rasterio.open(dst_tif) as src:
        assert max(src.width, src.height) <= 256
        assert src.compression.value.lower() == "deflate"


def test_optical_provider_ndvi_and_chip_cap() -> None:
    """Verifica el cálculo de NDVI/NDWI/ndvi_anomaly_delta y el tope de 512x512 px."""
    red = np.full((30, 30), 1000.0, dtype=np.float32)
    green = np.full((30, 30), 1200.0, dtype=np.float32)
    nir = np.full((30, 30), 2500.0, dtype=np.float32)

    inside_mask = np.zeros((30, 30), dtype=bool)
    inside_mask[10:20, 10:20] = True
    # Cropmark negativo sobre muro enterrado (menor vigor vegetal dentro)
    nir[inside_mask] = 1300.0

    spec = compute_spectral_indices_and_stats(red=red, green=green, nir=nir, inside_mask=inside_mask)
    assert spec["ndvi_mean"] is not None
    assert spec["ndwi_mean"] is not None
    assert spec["ndvi_anomaly_delta"] is not None
    assert spec["ndvi_anomaly_delta"] < -0.1

    big_rgb = np.zeros((900, 700, 3), dtype=np.uint8)
    capped = cap_rgb_chip_size(big_rgb, max_side_px=512)
    assert max(capped.shape[:2]) == 512


def test_composite_6_panels_with_optical_context(
    synthetic_posgar_dtm: Path,
    tmp_path: Path,
) -> None:
    """Verifica renderizado de lámina de 6 paneles cuando existe contexto óptico."""
    from src.core.relief_models import compute_slrm

    slrm_tif = compute_slrm(synthetic_posgar_dtm, tmp_path / "slrm.tif", radius_m=10.0)
    with rasterio.open(synthetic_posgar_dtm) as src:
        cx = (src.bounds.left + src.bounds.right) / 2.0
        cy = (src.bounds.bottom + src.bounds.top) / 2.0
    bbox = [cx - 20.0, cy - 20.0, cx + 20.0, cy + 20.0]

    optical_ctx = {
        "optical_provider_used": "sentinel2_stac",
        "rgb_image": np.full((128, 128, 3), 140, dtype=np.uint8),
        "ndvi_array": np.random.default_rng(7).uniform(0.0, 0.5, size=(30, 30)).astype(np.float32),
        "ndvi_mean": 0.25,
        "ndvi_anomaly_delta": -0.08,
        "ndwi_mean": -0.15,
        "patch_extent_posgar": (cx - 150.0, cx + 150.0, cy - 150.0, cy + 150.0),
    }

    out_6p = tmp_path / "comp_6p.png"
    render_candidate_composite(
        dtm_path=synthetic_posgar_dtm,
        slrm_path=slrm_tif,
        bbox_posgar=bbox,
        out_png_path=out_6p,
        centroid_posgar=[cx, cy],
        include_3d_render=False,
        optical_context=optical_ctx,
    )
    assert out_6p.exists() and out_6p.stat().st_size > 10_000


def test_discard_purges_zone_geojson_and_final_geojson(tmp_path: Path) -> None:
    """Verifica que un descarte elimina el candidato de MAPA_FINAL y de MAPA_PROSPECCION_{zona}."""
    rep_dir = tmp_path / "reports"
    rep_dir.mkdir(parents=True)
    img = tmp_path / "c.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 64)

    feat_base = {
        "type": "Feature",
        "id": "ARQ-TST-0001",
        "geometry": {"type": "Point", "coordinates": [-65.96, -24.45]},
        "properties": {
            "id": "ARQ-TST-0001",
            "anomaly_type": "recinto_ortogonal",
            "confidence": 0.85,
            "area_m2": 900.0,
            "rectangularity": 0.8,
            "circularity": 0.7,
            "mean_elevation_m": 1.1,
            "centroid_wgs84": [-65.96, -24.45],
            "composite_image_path": str(img),
        },
    }
    fc = {"type": "FeatureCollection", "metadata": {"confirmed_inedito_count": 1}, "features": [feat_base]}
    (rep_dir / "MAPA_FINAL_PROSPECCION.geojson").write_text(json.dumps(fc), encoding="utf-8")
    (rep_dir / "MAPA_PROSPECCION_ZONA_TEST.geojson").write_text(json.dumps(fc), encoding="utf-8")

    record_vlm_verdict(
        "ARQ-TST-0001",
        {
            "verdict": "NATURAL",
            "certainty_pct": 92,
            "functional_interpretation": "Lomada natural",
            "geomorphological_justification": "Domo continuo",
            "field_inspection_recommended": False,
            "backend": "test",
        },
        reports_dir=rep_dir,
        cache_dir=tmp_path / "cache",
    )

    final_fc = json.loads((rep_dir / "MAPA_FINAL_PROSPECCION.geojson").read_text(encoding="utf-8"))
    zone_fc = json.loads((rep_dir / "MAPA_PROSPECCION_ZONA_TEST.geojson").read_text(encoding="utf-8"))
    assert final_fc["features"] == []
    assert zone_fc["features"] == []
