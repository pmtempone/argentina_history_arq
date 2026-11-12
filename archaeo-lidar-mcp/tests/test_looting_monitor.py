"""Tests del módulo de vigilancia patrimonial (ALERTA_SAQUEO)."""

import geopandas as gpd  # noqa: F401  (verifica dependencia disponible)
import pytest

from src.core.known_sites import build_known_sites_gpkg
from src.core.looting_monitor import evaluate_looting_alert, math_sqrt


def _pit_props(lon: float, lat: float, area: float = 314.0, dz: float = -1.2) -> dict:
    """Props de un pozo circular de 20 m de diámetro (área = pi * r², dZ negativo)."""
    return {
        "anomaly_type": "estructura_hundida",
        "relief_sign": "negativo",
        "area_m2": area,
        "mean_elevation_m": dz,
        "circularity": 0.95,
        "aspect_ratio": 1.1,
        "centroid_wgs84": [lon, lat],
    }


@pytest.fixture
def known_gpkg(tmp_path):
    return build_known_sites_gpkg(out_gpkg_path=tmp_path / "known_sites.gpkg")


def test_alerta_saqueo_near_known_site(known_gpkg) -> None:
    """Pozo circular de 20 m a ~55 m de El Shincal -> ALERTA_SAQUEO con sitio identificado."""
    # El Shincal está en (-67.175, -27.687); un pozo a ~0.0005° de lat (~55 m)
    alert = evaluate_looting_alert(_pit_props(-67.1752, -27.6871), known_gpkg_path=known_gpkg)
    assert alert is not None
    assert alert["alert"] == "ALERTA_SAQUEO"
    assert alert["nearest_known_site"]["name"] == "El Shincal de Quimivil"
    assert alert["nearest_known_site"]["distance_m"] < 1000.0
    assert 5.0 <= alert["diameter_m"] <= 25.0
    assert "25.743" in alert["legal_note"]


def test_alerta_saqueo_requires_patrimonial_context(known_gpkg) -> None:
    """Mismo pozo lejos de todo sitio registrado y sin contexto OSM/IGN -> sin alerta."""
    alert = evaluate_looting_alert(_pit_props(-67.10, -27.60), known_gpkg_path=known_gpkg)
    assert alert is None


def test_alerta_saqueo_with_osm_historic_context(known_gpkg) -> None:
    """Sin sitio en el catálogo pero con `historic=archaeological_site` en OSM -> alerta."""
    osm = [{"type": "node", "id": 1, "tags": {"historic": "archaeological_site"}}]
    alert = evaluate_looting_alert(
        _pit_props(-67.10, -27.60),
        known_gpkg_path=known_gpkg,
        osm_matches=osm,
    )
    assert alert is not None
    assert alert["osm_historic_context"] is True


def test_zanja_lineal_and_positive_dz_not_alerts(known_gpkg) -> None:
    """Zanjas lineales (perfil de cárcava) y pozos con dZ positivo nunca generan alerta."""
    zanja = _pit_props(-67.1752, -27.6871)
    zanja["anomaly_type"] = "zanja_lineal"
    zanja["aspect_ratio"] = 6.0
    zanja["circularity"] = 0.60
    assert evaluate_looting_alert(zanja, known_gpkg_path=known_gpkg) is None

    # Pozo cerca del Shincal pero con dZ positivo (relieve positivo): no es saqueo
    assert evaluate_looting_alert(
        _pit_props(-67.1752, -27.6871, dz=+1.2), known_gpkg_path=known_gpkg
    ) is None


def test_diameter_out_of_range_not_alert(known_gpkg) -> None:
    """Un hundimiento de 40 m de diámetro excede el rango de pozo de huaquero (5-25 m)."""
    big = _pit_props(-67.1752, -27.6871, area=1256.0)  # d = 40 m
    assert evaluate_looting_alert(big, known_gpkg_path=known_gpkg) is None
    # Y uno de 2 m de diámetro (área ~3.1 m²) es demasiado chico
    tiny = _pit_props(-67.1752, -27.6871, area=3.1)
    assert evaluate_looting_alert(tiny, known_gpkg_path=known_gpkg) is None
