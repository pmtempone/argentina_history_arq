"""Tests unitarios de validación espacial (mocks de IGN WFS, Overpass OSM y OpenAlex API)."""

from pathlib import Path
from typing import Any, Dict

import geopandas as gpd
import httpx
import pytest
from shapely.geometry import Point

from src.core.literature_checker import check_academic_papers
from src.core.spatial_validator import validate_anomaly_async


def _build_mock_transport(
    ign_water_features: list[Dict[str, Any]],
    ign_settlement_features: list[Dict[str, Any]],
    osm_elements: list[Dict[str, Any]],
    openalex_works: list[Dict[str, Any]] | None = None,
) -> httpx.MockTransport:
    """Construye un MockTransport determinístico de httpx para interceptar WFS IGN, Overpass y OpenAlex."""

    def handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if "wms.ign.gob.ar" in url_str:
            if "ign%3Alinea_de_agua" in url_str or "ign:linea_de_agua" in url_str:
                return httpx.Response(
                    200,
                    json={"type": "FeatureCollection", "features": ign_water_features},
                )
            return httpx.Response(
                200,
                json={"type": "FeatureCollection", "features": ign_settlement_features},
            )
        if "overpass-api.de" in url_str:
            return httpx.Response(200, json={"elements": osm_elements})
        if "api.openalex.org" in url_str:
            return httpx.Response(200, json={"results": openalex_works or []})
        return httpx.Response(404, json={"error": "not found"})

    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_validate_candidato_inedito_with_water_distance() -> None:
    """Verifica que un candidato sin infraestructura moderna ni registro previo sea CANDIDATO_INEDITO."""
    lat, lon = -23.5800, -65.3500  # Quebrada de Humahuaca (POSGAR Faja 3 - EPSG:5345)

    # Río a ~100 metros al este (~0.001 grados de longitud)
    water_features = [
        {
            "type": "Feature",
            "id": "linea_de_agua.1",
            "geometry": {
                "type": "LineString",
                "coordinates": [[-65.3490, -23.5850], [-65.3490, -23.5750]],
            },
            "properties": {"nombre": "Río Grande"},
        }
    ]

    transport = _build_mock_transport(
        ign_water_features=water_features,
        ign_settlement_features=[],
        osm_elements=[],
    )

    async with httpx.AsyncClient(transport=transport) as client:
        result = await validate_anomaly_async(
            lat=lat,
            lon=lon,
            anomaly_id="ARQ-0001",
            http_client=client,
        )

    assert result.classification == "CANDIDATO_INEDITO"
    assert 80.0 <= result.distance_to_water_m <= 130.0
    assert len(result.ign_matches) == 1
    assert result.osm_matches == []


@pytest.mark.asyncio
async def test_validate_falso_positivo_moderno_from_osm() -> None:
    """Verifica que la presencia de un edificio o corral moderno en OSM clasifique FALSO_POSITIVO_MODERNO."""
    lat, lon = -27.4500, -68.1200

    osm_elements = [
        {
            "type": "way",
            "id": 998877,
            "tags": {"building": "farm_auxiliary", "barrier": "fence"},
        }
    ]

    transport = _build_mock_transport(
        ign_water_features=[],
        ign_settlement_features=[],
        osm_elements=osm_elements,
    )

    async with httpx.AsyncClient(transport=transport) as client:
        result = await validate_anomaly_async(
            lat=lat,
            lon=lon,
            anomaly_id="ARQ-0002",
            http_client=client,
        )

    assert result.classification == "FALSO_POSITIVO_MODERNO"
    assert len(result.osm_matches) == 1
    assert result.distance_to_water_m is None


@pytest.mark.asyncio
async def test_validate_sitio_registrado_from_local_gpkg_and_literature(tmp_path: Path) -> None:
    """Verifica que un sitio registrado en un GeoPackage local clasifique SITIO_REGISTRADO y consulte OpenAlex."""
    lat, lon = -23.5861, -65.3928  # Pucará de Tilcara

    gpkg_path = tmp_path / "known_sites.gpkg"
    gdf = gpd.GeoDataFrame(
        {"site_name": ["Pucará de Tilcara"], "period": ["Tardío / Inca"]},
        geometry=[Point(lon, lat)],
        crs="EPSG:4326",
    )
    gdf.to_file(gpkg_path, driver="GPKG")

    openalex_mock = [
        {
            "id": "https://openalex.org/W123456789",
            "title": "Arquitectura prehispánica en el Pucará de Tilcara, Quebrada de Humahuaca",
            "publication_year": 2021,
            "doi": "https://doi.org/10.1000/tilcara.2021",
            "authorships": [{"author": {"display_name": "María E. Albeck"}}],
        }
    ]

    transport = _build_mock_transport(
        ign_water_features=[],
        ign_settlement_features=[],
        osm_elements=[],
        openalex_works=openalex_mock,
    )

    async with httpx.AsyncClient(transport=transport) as client:
        val_res = await validate_anomaly_async(
            lat=lat,
            lon=lon,
            known_gpkg_path=gpkg_path,
            anomaly_id="ARQ-0003",
            http_client=client,
        )
        papers = await check_academic_papers(
            lat=lat,
            lon=lon,
            toponyms=["Tilcara", "Quebrada de Humahuaca"],
            http_client=client,
        )

    assert val_res.classification == "SITIO_REGISTRADO"
    assert len(papers) == 1
    assert "Pucará de Tilcara" in papers[0]["title"]
    assert papers[0]["publication_year"] == 2021
