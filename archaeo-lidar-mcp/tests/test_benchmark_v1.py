"""Tests unitarios para Etapa 0 (estados de evidencia) y Etapas 2/3 (Benchmark Nacional V1)."""

from pathlib import Path
import json
import sys

import pytest
from pydantic import ValidationError

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.core.baseline_manifest import map_verdict_to_lifecycle_state
from src.core.benchmark_v1 import (
    BenchmarkEntry,
    assign_spatial_block_splits,
    build_curated_benchmark_v1_dataset,
    compute_benchmark_metrics,
    should_abstain_prediction,
)
from src.core.dem_quality import DEMQualityProfile


def _make_profile(
    native_resolution_m: float = 1.0,
    has_synthetic_fallback_tag: bool = False,
    void_fraction: float = 0.0,
) -> DEMQualityProfile:
    tier = (
        "SYNTHETIC_UNSUITABLE"
        if has_synthetic_fallback_tag
        else ("HIGH_SUBMETRIC" if native_resolution_m <= 1.0 else "LOW_REGIONAL_30M")
    )
    return DEMQualityProfile(
        raster_path="/tmp/dummy.tif",
        provider_used="test_provider",
        model_type="DTM",
        crs_epsg=5345,
        grid_resolution_m=native_resolution_m,
        native_resolution_m=native_resolution_m,
        estimated_vertical_precision_m=0.10 if native_resolution_m <= 1.0 else 2.0,
        width_px=256,
        height_px=256,
        coverage_pct=round((1.0 - void_fraction) * 100.0, 2),
        void_fraction=void_fraction,
        border_nodata_fraction=0.0,
        has_synthetic_fallback_tag=has_synthetic_fallback_tag,
        min_detectable_area_m2=round(2.0 * (native_resolution_m ** 2), 2),
        suitable_for_microtopography=bool(not has_synthetic_fallback_tag and native_resolution_m <= 5.0),
        confidence_tier=tier,
        limitations_note="Perfil sintético de prueba.",
    )


def test_benchmark_entry_validation_and_sensor_detectable():
    """Valida reglas físicas de detectabilidad y obligatoriedad de categoría en negativos."""
    # Sitio de 100 m² en DEM global 30 m (piso = 1800 m²) -> no detectable por el sensor
    low_res_site = BenchmarkEntry(
        entry_id="POS_WALL_30M",
        region_block_id="BLK_TASTIL_N",
        biome="prepuna",
        is_positive_site=True,
        archaeo_confirmed=True,
        dem_resolution_m=30.0,
        expected_feature_area_m2=100.0,
    )
    assert low_res_site.sensor_detectable is False

    # Misma estructura de 100 m² en DEM UAV 1 m (piso = 2 m²) -> sí detectable
    uav_site = BenchmarkEntry(
        entry_id="POS_WALL_1M",
        region_block_id="BLK_TASTIL_N",
        biome="prepuna",
        is_positive_site=True,
        archaeo_confirmed=True,
        dem_resolution_m=1.0,
        expected_feature_area_m2=100.0,
    )
    assert uav_site.sensor_detectable is True

    # Negativo difícil válido
    hard_neg = BenchmarkEntry(
        entry_id="NEG_CAUCE_01",
        region_block_id="BLK_TASTIL_S",
        biome="prepuna",
        is_positive_site=False,
        negative_category="cauce_seco",
        dem_resolution_m=1.0,
        expected_feature_area_m2=240.0,
    )
    assert hard_neg.negative_category == "cauce_seco"

    # Negativo sin categoría debe fallar
    with pytest.raises(ValidationError):
        BenchmarkEntry(
            entry_id="NEG_SIN_CAT",
            region_block_id="BLK_X",
            biome="puna",
            is_positive_site=False,
            dem_resolution_m=1.0,
            expected_feature_area_m2=50.0,
        )

    # Positivo con negative_category debe fallar
    with pytest.raises(ValidationError):
        BenchmarkEntry(
            entry_id="POS_INVALID_CAT",
            region_block_id="BLK_X",
            biome="puna",
            is_positive_site=True,
            negative_category="cantera",
            dem_resolution_m=1.0,
            expected_feature_area_m2=50.0,
        )


def test_spatial_block_splits_no_leakage():
    """Roberts et al. (2017): ninguna unidad region_block_id puede dividirse entre splits."""
    entries = []
    block_defs = [
        ("BLK_QUEBRADA_A", "prepuna", 6),
        ("BLK_QUEBRADA_B", "prepuna", 4),
        ("BLK_YUNGAS_A", "yungas", 5),
        ("BLK_PATAGONIA_A", "estepa", 3),
        ("BLK_PATAGONIA_B", "estepa", 3),
        ("BLK_LITORAL_A", "humedal", 4),
    ]
    idx = 0
    for blk_id, biome, n_items in block_defs:
        for k in range(n_items):
            idx += 1
            is_pos = k % 2 == 0
            entries.append(
                BenchmarkEntry(
                    entry_id=f"ENT_{idx:03d}",
                    region_block_id=blk_id,
                    biome=biome,
                    is_positive_site=is_pos,
                    archaeo_confirmed=is_pos,
                    negative_category=None if is_pos else "carcava",
                    dem_resolution_m=1.0,
                    expected_feature_area_m2=80.0,
                )
            )

    split_run_1 = assign_spatial_block_splits(entries)
    split_run_2 = assign_spatial_block_splits(entries)

    # Determinismo exacto entre corridas
    assert [e.split for e in split_run_1] == [e.split for e in split_run_2]

    # Cobertura de los 3 splits
    all_splits = {e.split for e in split_run_1}
    assert all_splits == {"development", "validation", "blind_test"}

    # Cero fuga por bloque espacial: cada region_block_id pertenece a un único split
    block_splits = {}
    for e in split_run_1:
        block_splits.setdefault(e.region_block_id, set()).add(e.split)
    assert all(len(s) == 1 for s in block_splits.values())


def test_abstention_rules():
    """Verifica las reglas formales de abstención por escala, fallback sintético, vacíos y banda incierta."""
    # 1. DEM sintético -> abstención obligatoria
    abstain_syn, reason_syn = should_abstain_prediction(
        _make_profile(native_resolution_m=1.0, has_synthetic_fallback_tag=True),
        target_area_m2=150.0,
        calibrated_prob=0.95,
    )
    assert abstain_syn is True
    assert "INSUFFICIENT_SENSOR_DATA" in reason_syn

    # 2. DEM 30 m con estructura de 200 m² (< piso 1800 m²) -> abstención por escala
    abstain_scale, reason_scale = should_abstain_prediction(
        _make_profile(native_resolution_m=30.0),
        target_area_m2=200.0,
        calibrated_prob=0.90,
    )
    assert abstain_scale is True
    assert "BELOW_SENSOR_SCALE" in reason_scale

    # 3. Exceso de vacíos NoData > 25% -> abstención
    abstain_void, reason_void = should_abstain_prediction(
        _make_profile(native_resolution_m=1.0, void_fraction=0.35),
        target_area_m2=100.0,
        calibrated_prob=0.92,
    )
    assert abstain_void is True
    assert "EXCESSIVE_VOIDS" in reason_void

    # 4. Probabilidad dentro de banda ambigua [0.35, 0.65] -> abstención
    abstain_band, reason_band = should_abstain_prediction(
        _make_profile(native_resolution_m=1.0),
        target_area_m2=100.0,
        calibrated_prob=0.52,
    )
    assert abstain_band is True
    assert "UNCERTAIN_CALIBRATION_BAND" in reason_band

    # 5. Sensor adecuado y probabilidad alta -> decisión firme permitida
    abstain_ok, reason_ok = should_abstain_prediction(
        _make_profile(native_resolution_m=1.0),
        target_area_m2=100.0,
        calibrated_prob=0.92,
    )
    assert abstain_ok is False
    assert reason_ok == "CONFIDENT_DECISION"


def test_benchmark_metrics_excludes_undetectable_sites_and_computes_field_metrics():
    """Excluye sitios no detectables del denominador de recall y computa métricas de campaña."""
    evaluations = [
        # 2 TP detectados en prepuna
        {
            "is_positive_site": True,
            "sensor_detectable": True,
            "detected": True,
            "score": 0.92,
            "biome": "prepuna",
            "centroid_distance_m": 2.5,
            "spatial_iou": 0.75,
        },
        {
            "is_positive_site": True,
            "sensor_detectable": True,
            "detected": True,
            "score": 0.85,
            "biome": "estepa",
            "centroid_distance_m": 4.5,
            "spatial_iou": 0.65,
        },
        # 1 FN detectable perdido en prepuna
        {
            "is_positive_site": True,
            "sensor_detectable": True,
            "detected": False,
            "score": 0.25,
            "biome": "prepuna",
        },
        # 1 sitio sub-píxel (no detectable por el sensor) -> NO debe bajar el recall computable
        {
            "is_positive_site": True,
            "sensor_detectable": False,
            "detected": False,
            "score": 0.05,
            "biome": "yungas",
        },
        # 1 FP difícil (cantera) y 2 TN correctos
        {
            "is_positive_site": False,
            "detected": True,
            "score": 0.80,
            "biome": "estepa",
        },
        {
            "is_positive_site": False,
            "detected": False,
            "score": 0.15,
            "biome": "prepuna",
        },
        {
            "is_positive_site": False,
            "detected": False,
            "score": 0.10,
            "biome": "estepa",
        },
    ]

    metrics = compute_benchmark_metrics(evaluations, scanned_area_km2=4.0, k_values=(2, 5))

    assert metrics["excluded_undetectable_sites"] == 1
    assert metrics["tp"] == 2
    assert metrics["fn"] == 1
    assert metrics["fp"] == 1
    assert metrics["tn"] == 2
    assert metrics["site_recall"] == pytest.approx(2 / 3, abs=1e-4)
    lo, hi = metrics["site_recall_ci95"]
    assert 0.0 <= lo < metrics["site_recall"] < hi <= 1.0
    assert metrics["false_positives_per_km2"] == pytest.approx(0.25, abs=1e-4)
    # Top 2 ordenados por score: 0.92 (Pos), 0.85 (Pos) -> Precision@2 = 1.0
    assert metrics["precision_at_k"][2] == 1.0
    # Top 5: 2 Pos + 1 Neg (0.80) + 1 Pos (0.25) + 1 Neg (0.15) -> 3/5 = 0.6
    assert metrics["precision_at_k"][5] == pytest.approx(0.6, abs=1e-4)
    assert metrics["mean_centroid_distance_m"] == pytest.approx(3.5, abs=1e-4)
    assert metrics["mean_spatial_iou"] == pytest.approx(0.70, abs=1e-4)
    assert metrics["pr_auc"] is not None
    assert 0.0 <= metrics["brier_score"] <= 1.0
    assert "prepuna" in metrics["by_biome"]
    assert "estepa" in metrics["by_biome"]
    assert "yungas" not in metrics["by_biome"]  # único sitio en yungas era no detectable


def test_lifecycle_state_mapping_separates_algorithm_from_archaeology():
    """Un veredicto de IA nunca se promueve automáticamente a EXPERT_REVIEWED ni FIELD_CONFIRMED."""
    assert map_verdict_to_lifecycle_state(None) == "ALGORITHMIC_DETECTION"
    assert map_verdict_to_lifecycle_state("ANTROPICA") == "AI_PREASSESSMENT"
    assert map_verdict_to_lifecycle_state("PENDIENTE_REVISION") == "AI_PREASSESSMENT"
    assert map_verdict_to_lifecycle_state("NATURAL") == "REJECTED_NATURAL"
    assert map_verdict_to_lifecycle_state("ARTEFACTO") == "REJECTED_MODERN"
    assert map_verdict_to_lifecycle_state("DUDOSO") == "INCONCLUSIVE"
    # Revisión experta explícita requerida para EXPERT_REVIEWED
    assert map_verdict_to_lifecycle_state("ANTROPICA", expert_reviewed=True) == "EXPERT_REVIEWED"
    # Confirmación de campo explícita requerida para FIELD_CONFIRMED
    assert (
        map_verdict_to_lifecycle_state("ANTROPICA", expert_reviewed=True, field_confirmed=True)
        == "FIELD_CONFIRMED"
    )


def test_benchmark_entry_forces_unconfirmed_for_ai_and_published():
    """Controles VLM y referencias publicadas no pueden quedar como verdad arqueológica ni en blind_test."""
    ai_neg = BenchmarkEntry(
        entry_id="CTL_AI_01",
        region_block_id="BLK_X",
        biome="prepuna",
        is_positive_site=False,
        archaeo_confirmed=True,  # intento inválido de promover un descarte IA
        evidence_tier="AI_REJECTED_CANDIDATE",
        negative_category="geoforma_no_especificada",
        dem_resolution_m=30.0,
        expected_feature_area_m2=2500.0,
        eligible_for_blind_test=True,
    )
    assert ai_neg.archaeo_confirmed is False
    assert ai_neg.eligible_for_blind_test is False

    pub_ref = BenchmarkEntry(
        entry_id="PUB_01",
        region_block_id="BLK_Y",
        biome="prepuna",
        is_positive_site=True,
        archaeo_confirmed=True,
        evidence_tier="PUBLISHED_SITE_REFERENCE",
        coordinate_precision_m=100.0,
        dem_resolution_m=30.0,
        expected_feature_area_m2=10000.0,
        eligible_for_blind_test=True,
    )
    assert pub_ref.archaeo_confirmed is False
    assert pub_ref.eligible_for_blind_test is False


def test_curated_benchmark_dataset_no_duplication_and_no_blind_leak(tmp_path: Path):
    """Curaduría real: no duplica 86 geoformas, excluye sintéticos y deja blind_test=0."""
    out_json = tmp_path / "BENCHMARK_V1_DATASET.json"
    out_md = tmp_path / "BENCHMARK_V1_QUALITY_REPORT.md"
    res = build_curated_benchmark_v1_dataset(
        out_json_path=out_json,
        out_report_path=out_md,
    )
    assert out_json.exists()
    assert out_md.exists()

    audit = res["curation_audit"]
    assert audit["raw_descartes_count"] == 126
    assert audit["inventory_features_count"] == 86
    assert audit["inventory_strict_subset_of_descartes"] is True
    assert audit["linked_geoforms_merged_without_duplication"] == 86
    assert len(audit["excluded_synthetic_records"]) == 2
    assert audit["published_references_count"] == 9
    # 126 - 2 sintéticos = 124 controles + 9 referencias = 133 entradas (nunca 126 + 86 = 212)
    assert audit["active_curated_entries_count"] == 133
    assert audit["counts_by_split"]["blind_test"] == 0
    assert audit["counts_by_evidence_tier"] == {
        "AI_REJECTED_CANDIDATE": 124,
        "PUBLISHED_SITE_REFERENCE": 9,
    }

    payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert "descartes_vlm" in payload["source_provenance"]
    assert "inventario_geomorfologico" in payload["source_provenance"]
    assert "known_sites_published" in payload["source_provenance"]
    for entry in payload["entries"]:
        assert entry["archaeo_confirmed"] is False
        assert entry["eligible_for_blind_test"] is False
        assert entry["split"] in {"development", "validation"}

    # La partición por bloques espaciales no debe mezclar un mismo region_block_id entre splits
    block_splits = {}
    for entry in payload["entries"]:
        block_splits.setdefault(entry["region_block_id"], set()).add(entry["split"])
    assert all(len(s) == 1 for s in block_splits.values())


def test_benchmark_metrics_strict_ground_truth_guard():
    """compute_benchmark_metrics y el calibrador rechazan usar controles IA/sintéticos como verdad arqueológica."""
    from src.core.ml_calibrator import evaluate_calibrator_on_verified_benchmark

    mixed_rows = [
        {
            "is_positive_site": False,
            "detected": False,
            "score": 0.12,
            "biome": "prepuna",
            "evidence_tier": "AI_REJECTED_CANDIDATE",
        },
        {
            "is_positive_site": True,
            "sensor_detectable": True,
            "detected": True,
            "score": 0.90,
            "biome": "prepuna",
            "evidence_tier": "SYNTHETIC_POSITIVE",
        },
    ]

    non_strict = compute_benchmark_metrics(mixed_rows, scanned_area_km2=2.0, k_values=(2,))
    assert non_strict["evaluation_validity_scope"] == "INTERNAL_SYSTEM_CONTROL_NOT_ARCHAEOLOGICAL_GROUND_TRUTH"

    with pytest.raises(ValueError):
        compute_benchmark_metrics(mixed_rows, scanned_area_km2=2.0, require_verified_ground_truth=True)

    with pytest.raises(ValueError):
        evaluate_calibrator_on_verified_benchmark(mixed_rows, scanned_area_km2=2.0)

    # Al incluir filas verificadas por expertos/campo, el evaluador filtra únicamente esas
    verified_plus_ai = mixed_rows + [
        {
            "is_positive_site": True,
            "sensor_detectable": True,
            "detected": True,
            "score": 0.88,
            "biome": "prepuna",
            "evidence_tier": "FIELD_CONFIRMED",
        },
        {
            "is_positive_site": False,
            "detected": False,
            "score": 0.10,
            "biome": "prepuna",
            "evidence_tier": "EXPERT_REVIEWED",
        },
    ]
    res = evaluate_calibrator_on_verified_benchmark(verified_plus_ai, scanned_area_km2=2.0, k_values=(2,))
    assert res["evaluation_validity_scope"] == "VERIFIED_ARCHAEOLOGICAL_BENCHMARK"
    assert res["evaluable_count"] == 2
    assert res["site_recall"] == 1.0


@pytest.mark.asyncio
async def test_autonomous_prospector_preserves_inconclusive_on_unsuitable_dem(
    synthetic_posgar_dtm: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """Un DEM marcado SYNTHETIC_FALLBACK envía candidatos a INCONCLUSIVE sin perderlos ni confirmarlos."""
    import httpx
    import rasterio
    from src.autonomous_prospector import run_autonomous_prospector

    tagged_tif = tmp_path / "tagged_fallback_posgar.tif"
    with rasterio.open(synthetic_posgar_dtm) as src:
        prof = src.profile.copy()
        data = src.read(1)
    with rasterio.open(tagged_tif, "w", **prof) as dst:
        dst.write(data, 1)
        dst.update_tags(SYNTHETIC_FALLBACK="TRUE")

    raw_dir = tmp_path / "raw"
    proc_dir = tmp_path / "processed"
    rep_dir = tmp_path / "reports"
    raw_dir.mkdir()

    monkeypatch.setattr(
        "src.autonomous_prospector.fetch_elevation_tile",
        lambda target_zone, cache_dir, provider="auto", return_metadata=True: {
            "path": tagged_tif,
            "provider_used": "synthetic_fallback",
            "native_resolution_m": 0.5,
            "is_synthetic_fallback": True,
        },
    )

    transport = httpx.MockTransport(lambda req: httpx.Response(200, json={"results": []}))
    async with httpx.AsyncClient(transport=transport) as client:
        summary = await run_autonomous_prospector(
            target_zone="ZONA_1_TASTIL",
            window_size_m=200.0,
            overlap_ratio=0.15,
            min_confidence=0.70,
            min_elevation_m=0.20,
            optical_provider="none",
            cache_dir=raw_dir,
            processed_dir=proc_dir,
            reports_dir=rep_dir,
            http_client=client,
        )

    assert summary["dem_quality_profile"]["has_synthetic_fallback_tag"] is True
    assert summary["confirmed_count"] == 0
    assert summary["inconclusive_count"] >= 1
    assert len(summary["inconclusive_candidates"]) == summary["inconclusive_count"]
    for row in summary["inconclusive_candidates"]:
        assert row["lifecycle_state"] == "INCONCLUSIVE"
        assert row["algorithmic_detection_preserved"] is True
        assert "INSUFFICIENT_SENSOR_DATA" in row["abstention_reason"]

    # MAPA_PROSPECCION conserva las anomalías inconclusas sin promoverlas a features activas
    zone_map = json.loads((rep_dir / "MAPA_PROSPECCION_ZONA_1_TASTIL.geojson").read_text(encoding="utf-8"))
    assert zone_map["features"] == []
    assert zone_map["metadata"]["inconclusive_count"] == summary["inconclusive_count"]
    assert len(zone_map["inconclusive_features"]) == summary["inconclusive_count"]
    # Nunca debe convertirse en descarte negativo
    assert not (rep_dir / "DESCARTES_VLM.json").exists()
