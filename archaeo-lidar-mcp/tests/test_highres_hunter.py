"""Tests para el cazador autónomo de datasets LiDAR/UAV de alta resolución (HighResLidarHunter)."""

import io
from pathlib import Path
from typing import Any, Dict

import httpx
import numpy as np
import pytest
import rasterio
from pyproj import CRS
from rasterio.transform import from_origin

from src.core.highres_hunter import HighResLidarHunter


def _make_in_memory_geotiff_bytes(
    width: int = 240,
    height: int = 240,
    res_m: float = 0.50,
    epsg: int = 32719,
) -> bytes:
    """Genera un GeoTIFF en memoria con resolución `res_m` (ej. 0.50 m/px) y una estructura pircada sintética."""
    yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
    # Terreno suave con pendiente natural + recinto rectangular de 0.65m de altura y muros de 1m (2 px)
    terrain = 1850.0 + 0.02 * xx + 0.015 * yy
    wall_mask = (
        ((xx >= 90) & (xx <= 150) & (yy >= 90) & (yy <= 150))
        & ~((xx >= 94) & (xx <= 146) & (yy >= 94) & (yy <= 146))
    )
    terrain[wall_mask] += 0.65

    transform = from_origin(540000.0, 6510000.0, res_m, res_m)
    buf = io.BytesIO()
    with rasterio.open(
        buf,
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=1,
        dtype="float32",
        crs=CRS.from_epsg(epsg),
        transform=transform,
        nodata=-9999.0,
    ) as dst:
        dst.write(terrain, 1)
    return buf.getvalue()


@pytest.mark.asyncio
async def test_hunt_all_sources_parses_opentopo_zenodo_and_ign() -> None:
    """Verifica que HighResLidarHunter consulte OpenTopography, IGN y Zenodo y ordene por resolución."""

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "opentopography.org" in url:
            return httpx.Response(
                200,
                json={
                    "Datasets": [
                        {
                            "Dataset": {
                                "name": "Survey of the San Ramon Fault with Pleiades High-Res Imagery",
                                "shortName": "OTDS.022021.32719.1",
                                "fileFormat": "Point Cloud",
                                "url": "https://doi.org/10.5069/G9CC0XWZ",
                            }
                        }
                    ]
                },
            )
        if "wms.ign.gob.ar" in url:
            xml_body = (
                "<?xml version='1.0' encoding='UTF-8'?>"
                "<wcs:Capabilities xmlns:wcs='http://www.opengis.net/wcs/2.0'>"
                "<wcs:Contents><wcs:CoverageSummary>"
                "<wcs:CoverageId>ign__mde_ar_5m_salta</wcs:CoverageId>"
                "</wcs:CoverageSummary></wcs:Contents></wcs:Capabilities>"
            )
            return httpx.Response(200, text=xml_body)
        if "zenodo.org/api/records" in url:
            return httpx.Response(
                200,
                json={
                    "hits": {
                        "hits": [
                            {
                                "id": 999888,
                                "metadata": {
                                    "title": "UAV Drone Survey in Precordillera San Juan",
                                    "creators": [{"name": "CONICET Geomorphology"}],
                                },
                                "files": [
                                    {
                                        "key": "sanjuan_uav_05m.tif",
                                        "size": 12500000,
                                        "links": {
                                            "self": "https://zenodo.org/records/999888/files/sanjuan_uav_05m.tif?download=1"
                                        },
                                    }
                                ],
                            }
                        ]
                    }
                },
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        hunter = HighResLidarHunter(http_client=client)
        res = await hunter.hunt_all_sources(bbox=[-70.5, -34.0, -64.5, -22.0])

    assert res["status"] == "success"
    assert res["total_discovered"] >= 7
    assert res["highres_count_le_5m"] >= 6

    datasets = res["datasets"]
    # El primer dataset debe ser el de mayor resolución (0.25m)
    assert float(datasets[0]["resolution_m"]) <= 0.50
    ids = {d["id"] for d in datasets}
    assert "OTDS.022021.32719.1" in ids
    assert "IGN:ign__mde_ar_5m_salta" in ids
    assert any("999888" in i for i in ids)


@pytest.mark.asyncio
async def test_download_best_highres_preserves_submetric_resolution(tmp_path: Path) -> None:
    """Verifica la regla crítica: un GeoTIFF de 0.50 m/px NO se remuestrea a 2.0 m/px al proyectar a POSGAR 2007."""
    tif_bytes_05m = _make_in_memory_geotiff_bytes(width=300, height=300, res_m=0.50, epsg=32719)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=tif_bytes_05m)

    transport = httpx.MockTransport(handler)
    custom_datasets = [
        {
            "id": "TEST:SUBMETRIC_05M",
            "source": "Zenodo UAV Test",
            "title": "Test 0.50m Drone DTM",
            "institution": "CONICET",
            "region": "San Juan",
            "resolution_m": 0.50,
            "data_format": "GeoTIFF",
            "crs_epsg": "EPSG:32719",
            "bbox_wgs84": [-68.6, -31.6, -68.5, -31.5],
            "download_url": "https://example.org/test_05m.tif",
            "file_size_mb": 1.2,
            "direct_download": True,
        }
    ]

    async with httpx.AsyncClient(transport=transport) as client:
        hunter = HighResLidarHunter(http_client=client)
        dl_info = await hunter.download_best_highres_raster(
            datasets=custom_datasets,
            out_dir=tmp_path / "highres",
            target_epsg=5344,
            max_window_px=1500,
        )

    posgar_path = Path(dl_info["posgar_tif_path"])
    assert posgar_path.exists()
    assert np.isclose(dl_info["native_resolution_m"], 0.50, atol=0.02)
    assert np.isclose(dl_info["preserved_resolution_m"], 0.50, atol=0.02)

    with rasterio.open(posgar_path) as src:
        assert src.crs.to_epsg() == 5344
        res_x = abs(src.transform.a)
        # Regla crítica: DEBE mantener 0.50 m/px y NO remuestrear a 2.0 m/px
        assert np.isclose(res_x, 0.50, atol=0.02)
        assert src.width <= 1500 and src.height <= 1500
