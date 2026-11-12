"""Tests del juez pericial multimodal (VLM): fallback sin clave, Gemini mockeado y registro MCP."""

import json
from pathlib import Path
from typing import Any, Dict

import pytest

from src.core import vlm_judge
from src.core.vlm_judge import (
    VLMVerdict,
    evaluate_candidate_with_vlm,
    prepare_mcp_judgement,
    record_vlm_verdict,
)


def _make_png(path: Path) -> Path:
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 64)
    return path


def _seed_reports(rep_dir: Path, img: Path) -> None:
    rep_dir.mkdir(parents=True, exist_ok=True)
    fc: Dict[str, Any] = {
        "type": "FeatureCollection",
        "metadata": {},
        "features": [
            {
                "type": "Feature",
                "id": cid,
                "geometry": {"type": "Point", "coordinates": [-65.96, -24.45]},
                "properties": {
                    "id": cid,
                    "anomaly_type": "recinto_ortogonal",
                    "confidence": 0.8,
                    "area_m2": 900.0,
                    "rectangularity": 0.8,
                    "circularity": 0.7,
                    "mean_elevation_m": 1.2,
                    "centroid_wgs84": [-65.96, -24.45],
                    "composite_image_path": str(img),
                },
            }
            for cid in ("ARQ-0001", "ARQ-0002")
        ],
    }
    (rep_dir / "MAPA_FINAL_PROSPECCION.geojson").write_text(json.dumps(fc), encoding="utf-8")


def test_no_key_returns_pendiente(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Sin GEMINI_API_KEY nunca se inventa un veredicto."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    img = _make_png(tmp_path / "c.png")
    res = evaluate_candidate_with_vlm("ARQ-0001", img, {"area_m2": 10}, cache_dir=tmp_path / "cache")
    assert res["verdict"] == "PENDIENTE_REVISION"
    assert res["certainty_pct"] == 0
    assert not (tmp_path / "cache" / "ARQ-0001.json").exists()


def test_gemini_backend_mocked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Con clave, se usa el backend Gemini y el dictamen se cachea."""
    monkeypatch.setenv("GEMINI_API_KEY", "dummy")
    fake = VLMVerdict(
        verdict="NATURAL",
        certainty_pct=88,
        functional_interpretation="Lomada natural",
        geomorphological_justification="Perfil suave sin quiebres",
        field_inspection_recommended=False,
        backend="gemini:mock",
    )
    monkeypatch.setattr(vlm_judge, "_evaluate_with_gemini", lambda image, prompt: fake)
    img = _make_png(tmp_path / "c.png")
    res = evaluate_candidate_with_vlm("ARQ-0003", img, {}, cache_dir=tmp_path / "cache")
    assert res["verdict"] == "NATURAL"
    assert (tmp_path / "cache" / "ARQ-0003.json").exists()


def test_record_verdict_filters_and_updates_dossier(tmp_path: Path) -> None:
    """NATURAL/ARTEFACTO salen del GeoJSON, van a DESCARTES_VLM.json y el dossier tiene la sección 5."""
    rep_dir = tmp_path / "reports"
    img = _make_png(tmp_path / "c.png")
    _seed_reports(rep_dir, img)

    job = prepare_mcp_judgement("ARQ-0001", reports_dir=rep_dir)
    assert "Arqueólogo Espacial Senior" in job["prompt"]

    natural = {
        "verdict": "NATURAL",
        "certainty_pct": 90,
        "functional_interpretation": "Lomada",
        "geomorphological_justification": "Domo suave",
        "field_inspection_recommended": False,
        "backend": "mcp_host",
    }
    out = record_vlm_verdict("ARQ-0001", natural, reports_dir=rep_dir, cache_dir=tmp_path / "cache")
    assert out["discarded"] is True

    antropica = dict(natural, verdict="ANTROPICA", field_inspection_recommended=True)
    out2 = record_vlm_verdict("ARQ-0002", antropica, reports_dir=rep_dir, cache_dir=tmp_path / "cache")
    assert out2["discarded"] is False

    fc = json.loads((rep_dir / "MAPA_FINAL_PROSPECCION.geojson").read_text(encoding="utf-8"))
    assert [f["id"] for f in fc["features"]] == ["ARQ-0002"]
    disc = json.loads((rep_dir / "DESCARTES_VLM.json").read_text(encoding="utf-8"))
    assert "ARQ-0001" in disc["discarded"]
    md = Path(out["dossier_path"]).read_text(encoding="utf-8")
    assert "## 5. Juicio Pericial de Inteligencia Artificial Multimodal" in md
    assert "-65.96" not in md


def test_invalid_verdict_rejected(tmp_path: Path) -> None:
    rep_dir = tmp_path / "reports"
    _seed_reports(rep_dir, _make_png(tmp_path / "c.png"))
    with pytest.raises(Exception):
        record_vlm_verdict("ARQ-0001", {"verdict": "QUIZAS", "certainty_pct": 50}, reports_dir=rep_dir)
