"""Tests unitarios y de integración para data_fetcher y autonomous_prospector."""

import json
from pathlib import Path
from typing import Any, Dict

import httpx
import pytest
import rasterio

from src.autonomous_prospector import (
    generate_sliding_windows_metric,
    run_autonomous_prospector,
)
from src.core.data_fetcher import TARGET_ZONES, build_copernicus_cog_url, fetch_elevation_tile


def test_target_zones_and_cog_url() -> None:
    """Verifica las 3 zonas objetivo del NOA y la construcción de URLs de Copernicus GLO-30."""
    assert "ZONA_1_TASTIL" in TARGET_ZONES
    assert "ZONA_2_YOCAVIL" in TARGET_ZONES
    assert "ZONA_3_TINOGASTA" in TARGET_ZONES

    url_tastil = build_copernicus_cog_url(-24.45, -65.96)
    assert "Copernicus_DSM_COG_10_S25_00_W066_00_DEM" in url_tastil


def test_sliding_windows_generation() -> None:
    """Verifica la subdivisión en ventanas deslizantes de 500x500 m con 15% de overlap."""
    bounds = (3503000.0, 7295000.0, 3504000.0, 7296000.0)
    windows = generate_sliding_windows_metric(bounds, window_size_m=500.0, overlap_ratio=0.15)
    assert len(windows) >= 4
    first = windows[0]
    assert first[2] == 3503000.0
    assert first[3] == 7295000.0
    assert first[4] == 3503500.0
    assert first[5] == 7295500.0


@pytest.mark.asyncio
async def test_autonomous_prospector_end_to_end_synthetic(
    synthetic_posgar_dtm: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verifica el flujo completo de run_autonomous_prospector con mock de red para IGN/Overpass/OpenAlex."""
    raw_dir = tmp_path / "raw"
    proc_dir = tmp_path / "processed"
    rep_dir = tmp_path / "reports"
    raw_dir.mkdir(parents=True, exist_ok=True)

    # Hacer que fetch_elevation_tile devuelva nuestro DTM sintético en POSGAR 2007
    monkeypatch.setattr(
        "src.autonomous_prospector.fetch_elevation_tile",
        lambda target_zone, cache_dir: str(synthetic_posgar_dtm),
    )

    def mock_handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if "wms.ign.gob.ar" in url_str:
            return httpx.Response(200, json={"type": "FeatureCollection", "features": []})
        if "overpass-api.de" in url_str:
            return httpx.Response(200, json={"elements": []})
        if "api.openalex.org" in url_str:
            return httpx.Response(200, json={"results": []})
        return httpx.Response(404)

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as client:
        summary = await run_autonomous_prospector(
            target_zone="ZONA_1_TASTIL",
            window_size_m=200.0,
            overlap_ratio=0.15,
            min_confidence=0.70,
            min_elevation_m=0.20,
            cache_dir=raw_dir,
            processed_dir=proc_dir,
            reports_dir=rep_dir,
            http_client=client,
        )

    assert summary["status"] == "success"
    assert summary["confirmed_count"] >= 1
    geojson_file = Path(summary["final_map_geojson"])
    annex_file = Path(summary["confidential_annex_json"])
    assert geojson_file.exists()
    assert annex_file.exists()

    fc_data: Dict[str, Any] = json.loads(geojson_file.read_text(encoding="utf-8"))
    assert fc_data["type"] == "FeatureCollection"
    assert len(fc_data["features"]) == summary["confirmed_count"]
