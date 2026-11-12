"""Tests del inventario geomorfológico secundario (descartes NATURAL como insumo científico)."""

import json
from pathlib import Path

from src.core.geoform_inventory import (
    backfill_inventory_from_descartes,
    classify_geoform_subtype,
)
from src.core.vlm_judge import record_vlm_verdict


def test_classify_geoform_subtype_mapping() -> None:
    """La interpretación pericial mapea al subtipo geomorfológico correcto."""
    assert classify_geoform_subtype("Canal de escorrentía / quebrada encajonada natural") == "paleocauce"
    assert classify_geoform_subtype("Médano fósil / montículo aluvial de bajo relieve") == "medano_fosil"
    assert classify_geoform_subtype("Cordón morrénico / cresta nival coluvial alargada") == "morrena"
    assert classify_geoform_subtype("Escarpa de falla / banco estratigráfico sub-vertical") == "escarpa"
    assert classify_geoform_subtype("Lóbulo basáltico / prominencia volcánica en Puna") == "domo_volcanico"
    assert classify_geoform_subtype("Albardón fluvial lineal de borde de paleocauce") == "paleocauce"  # paleocauce precede
    assert classify_geoform_subtype("Interpretación sin vocabulario conocido") == "geoforma_no_clasificada"


def _make_reports_dir(tmp_path: Path) -> Path:
    reports = tmp_path / "reports"
    reports.mkdir()
    fc = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": "ARQ-GEO-0001",
                "geometry": {"type": "Point", "coordinates": [-67.1, -27.2]},
                "properties": {
                    "id": "ARQ-GEO-0001",
                    "anomaly_type": "estructura_hundida",
                    "area_m2": 2379.0,
                    "mean_elevation_m": -1.4,
                    "centroid_wgs84": [-67.1, -27.2],
                },
            },
        ],
    }
    (reports / "MAPA_FINAL_PROSPECCION.geojson").write_text(json.dumps(fc), encoding="utf-8")
    return reports


def test_record_natural_verdict_populates_inventory(tmp_path: Path) -> None:
    """Un dictamen NATURAL registrado alimenta el inventario; un ANTROPICA no."""
    reports = _make_reports_dir(tmp_path)
    verdict_natural = {
        "verdict": "NATURAL",
        "certainty_pct": 90,
        "functional_interpretation": "Canal de escorrentía / quebrada encajonada natural N-S",
        "geomorphological_justification": "Perfil V-U suave sin paredes construidas.",
        "field_inspection_recommended": False,
        "backend": "agente pericial in situ",
    }
    res = record_vlm_verdict(
        candidate_id="ARQ-GEO-0001",
        verdict_data=verdict_natural,
        reports_dir=reports,
    )
    assert res["discarded"] is True

    inventory_path = reports / "INVENTARIO_GEOMORFOLOGICO.geojson"
    assert inventory_path.exists()
    inv = json.loads(inventory_path.read_text(encoding="utf-8"))
    assert inv["metadata"]["feature_count"] == 1
    feat = inv["features"][0]
    assert feat["id"] == "ARQ-GEO-0001"
    assert feat["properties"]["geomorph_subtype"] == "paleocauce"
    assert feat["geometry"]["coordinates"] == [-67.1, -27.2]


def test_antropica_verdict_not_in_inventory(tmp_path: Path) -> None:
    """Solo los descartes NATURAL entran al inventario geomorfológico."""
    reports = _make_reports_dir(tmp_path)
    verdict_anthropica = {
        "verdict": "ANTROPICA",
        "certainty_pct": 92,
        "functional_interpretation": "Recinto ortogonal pircado",
        "geomorphological_justification": "Muros lineales en hillshade.",
        "field_inspection_recommended": True,
        "backend": "agente pericial in situ",
    }
    record_vlm_verdict(
        candidate_id="ARQ-GEO-0001",
        verdict_data=verdict_anthropica,
        reports_dir=reports,
    )
    assert not (reports / "INVENTARIO_GEOMORFOLOGICO.geojson").exists()


def test_backfill_inventory_from_descartes(tmp_path: Path) -> None:
    """El backfill reconstruye el inventario completo desde DESCARTES_VLM.json."""
    reports = tmp_path / "reports"
    reports.mkdir()
    fc = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": "ARQ-BF-0001",
                "properties": {
                    "id": "ARQ-BF-0001",
                    "anomaly_type": "estructura_hundida",
                    "area_m2": 400.0,
                    "mean_elevation_m": -1.0,
                    "centroid_wgs84": [-66.0, -27.0],
                },
            },
        ],
    }
    (reports / "MAPA_PROSPECCION_ZONA_BF.geojson").write_text(json.dumps(fc), encoding="utf-8")
    descartes = {
        "discarded": {
            "ARQ-BF-0001": {
                "anomaly_type": "estructura_hundida",
                "area_m2": 400.0,
                "mean_elevation_m": -1.0,
                "vlm_verdict": {
                    "verdict": "NATURAL",
                    "certainty_pct": 91,
                    "functional_interpretation": "Nicho de nivación en ladera alta",
                },
            },
            "ARQ-BF-0002": {  # sin mapa por zona, sin centroid: se omite
                "anomaly_type": "estructura_hundida",
                "area_m2": 300.0,
                "mean_elevation_m": -0.8,
                "vlm_verdict": {"verdict": "NATURAL", "certainty_pct": 88,
                                "functional_interpretation": "Vaguada"},
            },
            "ARQ-BF-0003": {  # ARTEFACTO: no entra
                "anomaly_type": "recinto_ortogonal",
                "area_m2": 700.0,
                "mean_elevation_m": 1.2,
                "vlm_verdict": {"verdict": "ARTEFACTO", "certainty_pct": 95,
                                "functional_interpretation": "Costura de tile"},
            },
        }
    }
    (reports / "DESCARTES_VLM.json").write_text(json.dumps(descartes), encoding="utf-8")

    out = backfill_inventory_from_descartes(reports_dir=reports)
    inv = json.loads(Path(out).read_text(encoding="utf-8"))
    assert inv["metadata"]["feature_count"] == 1  # solo el que tiene centroid
    assert inv["features"][0]["properties"]["geomorph_subtype"] == "morrena"
