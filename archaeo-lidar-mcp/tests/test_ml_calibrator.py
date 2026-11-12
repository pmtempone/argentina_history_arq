"""Tests del calibrador ML supervisado (probabilidad calibrada vs score heurístico)."""

import json
from pathlib import Path

import numpy as np
import pytest

from src.core.ml_calibrator import (
    FEATURE_NAMES,
    _generate_synthetic_positive_samples,
    build_dataset,
    extract_features,
    load_calibrator,
    score_candidate,
    train_calibrator,
)


def test_extract_features_with_and_without_raster_context() -> None:
    """El vector tiene 9 features; el contexto raster es opcional (NaN sin maestros)."""
    props = {
        "area_m2": 530.0,
        "mean_elevation_m": 1.67,
        "rectangularity": 0.92,
        "circularity": 0.70,
        "aspect_ratio": 1.5,
        "centroid_wgs84": [-65.9274, -27.2472],
    }
    feats = extract_features(props)
    assert sorted(feats.keys()) == sorted(FEATURE_NAMES)
    assert feats["area_m2"] == 530.0
    assert feats["dz_mean"] == pytest.approx(1.67)
    assert feats["dz_abs"] == pytest.approx(1.67)
    assert np.isnan(feats["slope_mean_deg"])  # sin raster maestro disponible

    # Con raster maestro: el SLRM/slope de la zona CIUDACITA se muestrea en la ventana
    slrm = Path("data/processed/zona_21_ciudacita_master_slrm.tif")
    slope = Path("data/processed/zona_21_ciudacita_master_slope.tif")
    if slrm.exists() and slope.exists():
        feats_ctx = extract_features(props, slrm_path=slrm, slope_path=slope)
        assert not np.isnan(feats_ctx["dz_extreme_window"])
        assert not np.isnan(feats_ctx["slope_mean_deg"])
        assert feats_ctx["slope_mean_deg"] >= 0.0

    # Inferencia de descriptores de forma desde la tipología (registros viejos sin props)
    legacy = {"area_m2": 100.0, "mean_elevation_m": -0.8, "anomaly_type": "estructura_hundida"}
    feats_legacy = extract_features(legacy)
    assert not np.isnan(feats_legacy["circularity"])
    assert feats_legacy["dz_abs"] == pytest.approx(0.8)


def test_synthetic_positive_samples_planted_truth(tmp_path: Path) -> None:
    """Los positivos sintéticos provienen de estructuras plantadas (verdad de campo conocida)."""
    samples, meta = _generate_synthetic_positive_samples(tmp_path, configs_limit=2)
    assert len(samples) >= 4  # >= 4 estructuras por config se recuperan
    assert all(s["label"] == 1 for s in samples)
    # Todos los positivos deben tener dZ coherente con el signo de la tipología
    for s, m in zip(samples, meta):
        assert m["source"] == "sintetico_plantado"
        if s["dz_mean"] < 0:
            assert m["anomaly_type"] in {"estructura_hundida", "zanja_lineal"}
        else:
            assert m["anomaly_type"] in {"recinto_ortogonal", "estructura_circular", "terraza_lineal"}


def test_train_calibrator_end_to_end(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Entrenamiento completo con dataset mini (2 configs sintéticas + descartes mini)."""
    # Descartes mini: 2 hard negatives con props completas en el mapa por zona
    reports = tmp_path / "reports"
    reports.mkdir()
    fc = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": "ARQ-TST-0001",
                "properties": {
                    "id": "ARQ-TST-0001",
                    "anomaly_type": "recinto_ortogonal",
                    "area_m2": 4009.0,
                    "mean_elevation_m": 1.42,
                    "rectangularity": 0.59,
                    "circularity": 0.53,
                    "aspect_ratio": 1.4,
                    "centroid_wgs84": [-66.0, -27.0],
                },
            },
            {
                "type": "Feature",
                "id": "ARQ-TST-0002",
                "properties": {
                    "id": "ARQ-TST-0002",
                    "anomaly_type": "estructura_circular",
                    "area_m2": 3600.0,
                    "mean_elevation_m": 1.15,
                    "rectangularity": 0.62,
                    "circularity": 0.80,
                    "aspect_ratio": 1.2,
                    "centroid_wgs84": [-66.01, -27.01],
                },
            },
            {
                "type": "Feature",
                "id": "ARQ-TST-0003",
                "properties": {
                    "id": "ARQ-TST-0003",
                    "anomaly_type": "terraza_lineal",
                    "area_m2": 1400.0,
                    "mean_elevation_m": 1.49,
                    "rectangularity": 0.71,
                    "circularity": 0.42,
                    "aspect_ratio": 5.0,
                    "centroid_wgs84": [-66.02, -27.02],
                },
            },
        ],
    }
    (reports / "MAPA_PROSPECCION_ZONA_TEST.geojson").write_text(json.dumps(fc), encoding="utf-8")
    descartes = {
        "discarded": {
            "ARQ-TST-0001": {"anomaly_type": "recinto_ortogonal", "area_m2": 4009.0,
                             "mean_elevation_m": 1.42, "vlm_verdict": {"verdict": "NATURAL"}},
            "ARQ-TST-0002": {"anomaly_type": "estructura_circular", "area_m2": 3600.0,
                             "mean_elevation_m": 1.15, "vlm_verdict": {"verdict": "ARTEFACTO"}},
            "ARQ-TST-0003": {"anomaly_type": "terraza_lineal", "area_m2": 1400.0,
                             "mean_elevation_m": 1.49, "vlm_verdict": {"verdict": "NATURAL"}},
        }
    }
    (reports / "DESCARTES_VLM.json").write_text(json.dumps(descartes), encoding="utf-8")

    # Limitar los configs sintéticos para acelerar el test
    monkeypatch.setattr(
        "src.core.ml_calibrator._generate_synthetic_positive_samples",
        lambda *a, **kw: _generate_synthetic_positive_samples(
            kw.get("working_dir") or (a[0] if a else None), seed=kw.get("seed", 42), configs_limit=2
        ),
    )

    result = train_calibrator(
        reports_dir=reports,
        model_path=tmp_path / "ml_calibrator.joblib",
        report_path=tmp_path / "ML_BENCHMARK_METRICS.md",
        positive_workdir=tmp_path / "positives",
    )

    assert result["n_negatives"] == 3
    assert result["n_positives"] >= 4
    metrics = result["cv_metrics"]
    assert 0.0 <= metrics["precision_class1"] <= 1.0
    assert 0.0 <= metrics["recall_class1"] <= 1.0
    assert 0.0 <= metrics["f1_class1"] <= 1.0
    assert 0.0 <= metrics["macro"]["f1"] <= 1.0
    # Importancias normalizadas a 1 en total
    assert sum(result["feature_importances"].values()) == pytest.approx(1.0, abs=0.05)

    # Reporte con las secciones exigidas
    report_text = (tmp_path / "ML_BENCHMARK_METRICS.md").read_text(encoding="utf-8")
    for token in ("Precision", "Recall", "Importancia", "Limitaciones"):
        assert token in report_text

    # Scoring end-to-end del modelo persistido
    bundle = load_calibrator(tmp_path / "ml_calibrator.joblib")
    assert bundle is not None
    prob_pos = score_candidate(
        {
            "area_m2": 112.0,
            "mean_elevation_m": 0.6,
            "rectangularity": 0.92,
            "circularity": 0.65,
            "aspect_ratio": 1.75,
            "centroid_wgs84": None,
        },
        model=bundle,
    )
    assert prob_pos is not None
    assert 0.0 <= prob_pos <= 1.0
