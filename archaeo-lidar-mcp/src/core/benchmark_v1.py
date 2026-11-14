"""Etapas 2 y 3 — Diseño del Benchmark Nacional V1, partición espacial por bloques y métricas arqueológicas.

Implementa:
- Esquema `BenchmarkEntry` con niveles explícitos de evidencia (`EvidenceTierLiteral`:
  `AI_REJECTED_CANDIDATE`, `PUBLISHED_SITE_REFERENCE`, `EXPERT_REVIEWED`, `FIELD_CONFIRMED`),
  clases de negativos difíciles (geoformas naturales, estructuras modernas, artefactos DEM y
  geoformas no especificadas) y bandera `sensor_detectable` según resolución física del DEM.
- Curaduría trazable de datos piloto locales (`build_curated_benchmark_v1_dataset`) vinculando
  sin duplicación `DESCARTES_VLM.json`, `INVENTARIO_GEOMORFOLOGICO.geojson` y
  `known_sites_published.csv` con hashes SHA-256 de procedencia.
- Partición espacial por bloques (`assign_spatial_block_splits`) siguiendo Roberts et al.
  (2017), garantizando cero fuga espacial y prohibiendo asignar a `blind_test` muestras no
  elegibles cuando `enforce_blind_eligibility=True`.
- Regla formal de abstención (`should_abstain_prediction`).
- Cálculo de métricas (`compute_benchmark_metrics`) con guardia de validez científica
  (`require_verified_ground_truth`) para no reportar validez arqueológica sobre etiquetas IA
  o sintéticas.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Set, Tuple

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sklearn.metrics import average_precision_score

from src.core.dem_quality import DEMQualityProfile

HardNegativeCategory = Literal[
    # Geoformas naturales difíciles (5)
    "cauce_seco",
    "carcava",
    "terraza_fluvial",
    "cono_deyeccion",
    "afloramiento_rocoso",
    # Estructuras modernas o antrópicas recientes (5)
    "cantera",
    "terraplen_moderno",
    "camino_rural",
    "obra_hidraulica",
    "terraza_agricola_reciente",
    # Controles técnicos sin sobre-clasificación artificial
    "artefacto_dem_interpolacion",
    "geoforma_no_especificada",
]

NATURAL_HARD_NEGATIVES: Tuple[str, ...] = (
    "cauce_seco",
    "carcava",
    "terraza_fluvial",
    "cono_deyeccion",
    "afloramiento_rocoso",
)

MODERN_HARD_NEGATIVES: Tuple[str, ...] = (
    "cantera",
    "terraplen_moderno",
    "camino_rural",
    "obra_hidraulica",
    "terraza_agricola_reciente",
)

EvidenceTierLiteral = Literal[
    "AI_REJECTED_CANDIDATE",
    "PUBLISHED_SITE_REFERENCE",
    "EXPERT_REVIEWED",
    "FIELD_CONFIRMED",
]

SplitLiteral = Literal["development", "validation", "blind_test"]

_UNVERIFIED_TIERS: Set[str] = {
    "AI_REJECTED_CANDIDATE",
    "PUBLISHED_SITE_REFERENCE",
    "SYNTHETIC_POSITIVE",
}

_ZONE_BIOME_FALLBACK: Dict[str, str] = {
    "ZONA_1_TASTIL": "noa_quebradas_valles",
    "ZONA_2_YOCAVIL": "noa_quebradas_valles",
    "ZONA_3_TINOGASTA": "noa_quebradas_valles",
    "ZONA_4_TOLOMBON": "noa_quebradas_valles",
    "ZONA_5_LAPAYA": "noa_quebradas_valles",
    "ZONA_6_TILCARA": "noa_quebradas_valles",
    "ZONA_7_ACONQUIJA": "noa_quebradas_valles",
    "ZONA_8_SHINCAL": "noa_quebradas_valles",
    "ZONA_9_ALUMBRERA": "puna_alta_montana",
    "ZONA_10_RINCONADA": "puna_alta_montana",
    "ZONA_11_LACUEVA": "noa_quebradas_valles",
    "ZONA_12_USPALLATA": "andes_cuyanos",
    "ZONA_13_SOMUNCURA": "meseta_patagonica",
    "ZONA_14_LLULLAILLACO": "puna_alta_montana",
    "ZONA_15_VOLCAN_GALAN": "puna_alta_montana",
    "ZONA_16_LAGO_BUENOS_AIRES": "meseta_patagonica",
    "PATAGONIA_GEN": "meseta_patagonica",
    "HIGHRES_SAN_JUAN_UAV": "cuyo_precordillera",
    "HIGHRES_ZENODO_3383227": "cuyo_monte",
}

_GEOMORPH_CONSERVATIVE_MAP: Dict[str, HardNegativeCategory] = {
    "paleocauce": "cauce_seco",
    "cono_aluvial": "cono_deyeccion",
    "roca_fracturada": "afloramiento_rocoso",
    "domo_volcanico": "afloramiento_rocoso",
    "canchal": "afloramiento_rocoso",
    "albardon": "terraza_fluvial",
}


class BenchmarkEntry(BaseModel):
    """Registro auditado del Benchmark Nacional V1 (con trazabilidad de nivel de evidencia)."""

    model_config = ConfigDict(extra="forbid")

    entry_id: str = Field(..., min_length=1, description="Identificador único de la muestra.")
    region_block_id: str = Field(
        ...,
        min_length=1,
        description="Bloque geográfico contiguo para validación bloqueada (Roberts et al. 2017).",
    )
    biome: str = Field(..., min_length=1, description="Bioma / región morfoestructural.")
    is_positive_site: bool = Field(
        ..., description="True si corresponde a evidencia arqueológica de referencia."
    )
    archaeo_confirmed: bool = Field(
        default=False,
        description="True únicamente si fue verificado en campo o por especialista independiente.",
    )
    evidence_tier: EvidenceTierLiteral = Field(
        default="EXPERT_REVIEWED",
        description="Nivel epistémico de la etiqueta (separa controles IA/publicados de verdad de campo).",
    )
    source_origin: str = Field(
        default="curated_benchmark",
        min_length=1,
        description="Archivo o fuente primaria de procedencia del registro.",
    )
    linked_geoform_id: Optional[str] = Field(
        default=None,
        description="ID en INVENTARIO_GEOMORFOLOGICO si deriva del mismo descarte VLM (evita duplicación).",
    )
    geomorph_subtype: Optional[str] = Field(
        default=None,
        description="Subtipo geomorfológico original registrado en el inventario asociado.",
    )
    coordinate_precision_m: Optional[float] = Field(
        default=None,
        gt=0.0,
        description="Incertidumbre espacial declarada de la coordenada de referencia (metros).",
    )
    eligible_for_blind_test: bool = Field(
        default=True,
        description="False para muestras ya usadas en ajuste del sistema o catálogos internos aproximados.",
    )
    sensor_detectable: Optional[bool] = Field(
        default=None,
        description=(
            "True si expected_feature_area_m2 >= 2 * dem_resolution_m^2. "
            "Se infiere automáticamente si se omite."
        ),
    )
    negative_category: Optional[HardNegativeCategory] = Field(
        default=None,
        description="Categoría obligatoria de negativo difícil cuando is_positive_site=False.",
    )
    dem_resolution_m: float = Field(
        ..., gt=0.0, description="Resolución física nativa del DEM evaluado (metros)."
    )
    expected_feature_area_m2: float = Field(
        ..., gt=0.0, description="Área esperada de la estructura o geoforma objetivo (m²)."
    )
    split: Optional[SplitLiteral] = Field(
        default=None,
        description="Subconjunto asignado por bloque espacial (development/validation/blind_test).",
    )
    notes: Optional[str] = Field(default=None, description="Notas de curaduría o procedencia.")

    @model_validator(mode="after")
    def _validate_and_derive(self) -> "BenchmarkEntry":
        if not self.is_positive_site and self.negative_category is None:
            raise ValueError(
                f"La entrada negativa '{self.entry_id}' requiere negative_category explícita."
            )
        if self.is_positive_site and self.negative_category is not None:
            raise ValueError(
                f"La entrada positiva '{self.entry_id}' no debe declarar negative_category."
            )
        if self.evidence_tier in {"AI_REJECTED_CANDIDATE", "PUBLISHED_SITE_REFERENCE"}:
            self.archaeo_confirmed = False
            self.eligible_for_blind_test = False
        if self.sensor_detectable is None:
            physical_floor_m2 = 2.0 * (self.dem_resolution_m ** 2)
            self.sensor_detectable = bool(self.expected_feature_area_m2 >= physical_floor_m2)
        return self


def _deterministic_block_sort_key(block_id: str, count: int) -> Tuple[int, str]:
    digest = hashlib.sha256(block_id.encode("utf-8")).hexdigest()
    return (-count, digest)


def assign_spatial_block_splits(
    entries: List[BenchmarkEntry],
    ratios: Tuple[float, float, float] = (0.60, 0.20, 0.20),
    enforce_blind_eligibility: bool = False,
) -> List[BenchmarkEntry]:
    """Asigna `development`, `validation` y `blind_test` por bloque espacial completo.

    Sigue Roberts et al. (2017): todas las entradas que comparten `region_block_id`
    se asignan al mismo split para evitar fuga por autocorrelación espacial.
    Si `enforce_blind_eligibility=True`, los bloques que contienen muestras con
    `eligible_for_blind_test=False` solo pueden ir a `development` o `validation`.
    """
    if not entries:
        return []

    if len(ratios) != 3 or any(r <= 0.0 for r in ratios) or not math.isclose(sum(ratios), 1.0, abs_tol=1e-6):
        raise ValueError(f"ratios inválidos {ratios}: deben ser 3 valores positivos que sumen 1.0.")

    split_names: Tuple[SplitLiteral, SplitLiteral, SplitLiteral] = (
        "development",
        "validation",
        "blind_test",
    )

    by_block: Dict[str, List[BenchmarkEntry]] = defaultdict(list)
    for entry in entries:
        by_block[entry.region_block_id].append(entry)

    sorted_blocks = sorted(
        by_block.items(),
        key=lambda item: _deterministic_block_sort_key(item[0], len(item[1])),
    )

    total_n = len(entries)
    block_to_split: Dict[str, SplitLiteral] = {}

    if not enforce_blind_eligibility:
        targets = [r * total_n for r in ratios]
        assigned_counts = [0, 0, 0]
        if len(sorted_blocks) >= 3:
            for split_idx, block_idx in zip((0, 2, 1), (0, 1, 2)):
                blk_id, blk_entries = sorted_blocks[block_idx]
                block_to_split[blk_id] = split_names[split_idx]
                assigned_counts[split_idx] += len(blk_entries)
            remaining = sorted_blocks[3:]
        else:
            remaining = sorted_blocks

        for blk_id, blk_entries in remaining:
            deficits = [
                (targets[i] - assigned_counts[i]) / max(targets[i], 1.0) for i in range(3)
            ]
            best_split_idx = int(np.argmax(deficits))
            block_to_split[blk_id] = split_names[best_split_idx]
            assigned_counts[best_split_idx] += len(blk_entries)
    else:
        blind_ok_blocks = [
            (b_id, b_list)
            for b_id, b_list in sorted_blocks
            if all(e.eligible_for_blind_test for e in b_list)
        ]
        non_blind_blocks = [
            (b_id, b_list)
            for b_id, b_list in sorted_blocks
            if not all(e.eligible_for_blind_test for e in b_list)
        ]

        blind_target = ratios[2] * total_n if blind_ok_blocks else 0.0
        blind_assigned = 0
        dev_val_pool: List[Tuple[str, List[BenchmarkEntry]]] = list(non_blind_blocks)

        if blind_ok_blocks:
            # Asignar bloques independientes a blind_test hasta acercarse al cupo
            for b_id, b_list in blind_ok_blocks:
                if blind_assigned == 0 or (blind_assigned + len(b_list) <= blind_target * 1.15):
                    block_to_split[b_id] = "blind_test"
                    blind_assigned += len(b_list)
                else:
                    dev_val_pool.append((b_id, b_list))
            dev_val_pool = sorted(
                dev_val_pool,
                key=lambda item: _deterministic_block_sort_key(item[0], len(item[1])),
            )

        pool_n = sum(len(b_list) for _, b_list in dev_val_pool)
        dv_sum = ratios[0] + ratios[1]
        dv_targets = [(ratios[0] / dv_sum) * max(pool_n, 1), (ratios[1] / dv_sum) * max(pool_n, 1)]
        dv_counts = [0, 0]

        if len(dev_val_pool) >= 2:
            for split_idx, block_idx in ((0, 0), (1, 1)):
                blk_id, blk_entries = dev_val_pool[block_idx]
                block_to_split[blk_id] = split_names[split_idx]
                dv_counts[split_idx] += len(blk_entries)
            rem_dv = dev_val_pool[2:]
        else:
            rem_dv = dev_val_pool

        for blk_id, blk_entries in rem_dv:
            deficits = [
                (dv_targets[i] - dv_counts[i]) / max(dv_targets[i], 1.0) for i in range(2)
            ]
            best_idx = int(np.argmax(deficits))
            block_to_split[blk_id] = split_names[best_idx]
            dv_counts[best_idx] += len(blk_entries)

    return [
        entry.model_copy(update={"split": block_to_split[entry.region_block_id]})
        for entry in entries
    ]


def should_abstain_prediction(
    dem_profile: DEMQualityProfile,
    target_area_m2: float,
    calibrated_prob: float,
    uncertainty_band: Tuple[float, float] = (0.35, 0.65),
) -> Tuple[bool, str]:
    """Determina si el sistema debe abstenerse en lugar de emitir predicción firme.

    Criterios de abstención (Etapa 1.1 + Etapa 3):
    1. DEM proveniente de fallback sintético offline o marcado como SYNTHETIC_UNSUITABLE.
    2. Fracción excesiva de vacíos (NoData > 25 %).
    3. Estructura objetivo por debajo del piso físico detectable del sensor
       (`target_area_m2 < dem_profile.min_detectable_area_m2`).
    4. Probabilidad calibrada dentro de la banda de incertidumbre operativa.
    """
    if dem_profile.has_synthetic_fallback_tag or dem_profile.confidence_tier == "SYNTHETIC_UNSUITABLE":
        return True, "INSUFFICIENT_SENSOR_DATA: DEM sintético o no apto para inferencia topográfica."

    if dem_profile.void_fraction > 0.25:
        return (
            True,
            f"EXCESSIVE_VOIDS: Fracción de vacíos ({dem_profile.void_fraction:.2f}) supera 0.25.",
        )

    if target_area_m2 < dem_profile.min_detectable_area_m2:
        return (
            True,
            (
                f"BELOW_SENSOR_SCALE: Estructura objetivo ({target_area_m2:.1f} m²) < "
                f"piso físico detectable ({dem_profile.min_detectable_area_m2:.1f} m² a "
                f"{dem_profile.native_resolution_m:.1f} m)."
            ),
        )

    low, high = uncertainty_band
    if low <= calibrated_prob <= high:
        return (
            True,
            (
                f"UNCERTAIN_CALIBRATION_BAND: Probabilidad ({calibrated_prob:.3f}) en banda "
                f"ambigua [{low:.2f}, {high:.2f}]."
            ),
        )

    return False, "CONFIDENT_DECISION"


def _wilson_ci95(successes: int, total: int) -> Optional[Tuple[float, float]]:
    """Intervalo de confianza del 95% de Wilson para proporciones con n pequeño."""
    if total <= 0:
        return None
    z = 1.959963984540054
    p = successes / total
    z2 = z * z
    denom = 1.0 + z2 / total
    center = (p + z2 / (2.0 * total)) / denom
    half = (z * math.sqrt((p * (1.0 - p) + z2 / (4.0 * total)) / total)) / denom
    return (round(max(0.0, center - half), 4), round(min(1.0, center + half), 4))


def _compute_calibration_bins(
    y_true: np.ndarray, y_prob: np.ndarray, n_bins: int = 5
) -> List[Dict[str, Any]]:
    if len(y_true) == 0:
        return []
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    bins_out: List[Dict[str, Any]] = []
    for i in range(n_bins):
        lo, hi = float(edges[i]), float(edges[i + 1])
        if i < n_bins - 1:
            mask = (y_prob >= lo) & (y_prob < hi)
        else:
            mask = (y_prob >= lo) & (y_prob <= hi)
        count = int(np.sum(mask))
        if count == 0:
            continue
        bins_out.append(
            {
                "bin_range": [round(lo, 2), round(hi, 2)],
                "count": count,
                "mean_pred_prob": round(float(np.mean(y_prob[mask])), 4),
                "empirical_positive_rate": round(float(np.mean(y_true[mask])), 4),
            }
        )
    return bins_out


def compute_benchmark_metrics(
    evaluations: List[Dict[str, Any]],
    scanned_area_km2: float,
    k_values: Tuple[int, ...] = (5, 10),
    require_verified_ground_truth: bool = False,
) -> Dict[str, Any]:
    """Calcula métricas orientadas a validación arqueológica y planificación de campaña.

    Sitios positivos con `sensor_detectable=False` se contabilizan en
    `excluded_undetectable_sites` y se excluyen del cálculo de `site_recall`.
    Si `require_verified_ground_truth=True`, rechaza evaluaciones basadas en
    controles IA (`AI_REJECTED_CANDIDATE`), `PUBLISHED_SITE_REFERENCE` o
    `SYNTHETIC_POSITIVE` para impedir confundir consistencia interna con validez arqueológica.
    """
    if scanned_area_km2 <= 0.0:
        raise ValueError(f"scanned_area_km2 debe ser > 0, recibido: {scanned_area_km2}")

    present_tiers = {
        str(ev["evidence_tier"])
        for ev in evaluations
        if ev.get("evidence_tier") is not None
    }
    unverified_present = sorted(present_tiers & _UNVERIFIED_TIERS)
    if require_verified_ground_truth and unverified_present:
        raise ValueError(
            "Evaluación científica rechazada: contiene registros sin verificación "
            f"experta ni de campo ({unverified_present}). Use solo EXPERT_REVIEWED / FIELD_CONFIRMED."
        )

    # Por defecto (cuando no se declara evidence_tier en tests unitarios), asume benchmark controlado;
    # si hay etiquetas IA/sintéticas/referencias aproximadas, fuerza etiqueta de alcance restringido.
    if unverified_present:
        validity_scope = "INTERNAL_SYSTEM_CONTROL_NOT_ARCHAEOLOGICAL_GROUND_TRUTH"
    else:
        validity_scope = "VERIFIED_ARCHAEOLOGICAL_BENCHMARK"

    excluded_undetectable = [
        ev for ev in evaluations if bool(ev.get("is_positive_site")) and not bool(ev.get("sensor_detectable", True))
    ]
    evaluable = [
        ev
        for ev in evaluations
        if (not bool(ev.get("is_positive_site"))) or bool(ev.get("sensor_detectable", True))
    ]

    positives = [ev for ev in evaluable if bool(ev.get("is_positive_site"))]
    negatives = [ev for ev in evaluable if not bool(ev.get("is_positive_site"))]

    tp = sum(1 for ev in positives if bool(ev.get("detected")))
    fn = len(positives) - tp
    fp = sum(1 for ev in negatives if bool(ev.get("detected")))
    tn = len(negatives) - fp

    site_recall = round(tp / len(positives), 4) if positives else None
    site_recall_ci95 = _wilson_ci95(tp, len(positives))
    fp_per_km2 = round(fp / scanned_area_km2, 4)

    scored = sorted(
        evaluable,
        key=lambda ev: float(ev.get("score", ev.get("prob", 1.0 if ev.get("detected") else 0.0))),
        reverse=True,
    )
    precision_at_k: Dict[int, Optional[float]] = {}
    for k in k_values:
        if not scored or k <= 0:
            precision_at_k[int(k)] = None
        else:
            top_k = scored[: min(k, len(scored))]
            hits = sum(1 for ev in top_k if bool(ev.get("is_positive_site")))
            precision_at_k[int(k)] = round(hits / len(top_k), 4)

    centroid_dists = [
        float(ev["centroid_distance_m"])
        for ev in positives
        if bool(ev.get("detected")) and ev.get("centroid_distance_m") is not None
    ]
    spatial_ious = [
        float(ev["spatial_iou"])
        for ev in positives
        if bool(ev.get("detected")) and ev.get("spatial_iou") is not None
    ]

    mean_centroid_dist = round(float(np.mean(centroid_dists)), 3) if centroid_dists else None
    mean_spatial_iou = round(float(np.mean(spatial_ious)), 4) if spatial_ious else None

    if evaluable:
        y_true = np.array([1 if ev.get("is_positive_site") else 0 for ev in evaluable], dtype=float)
        y_score = np.array(
            [
                float(np.clip(ev.get("score", ev.get("prob", 1.0 if ev.get("detected") else 0.0)), 0.0, 1.0))
                for ev in evaluable
            ],
            dtype=float,
        )
        brier_score = round(float(np.mean((y_score - y_true) ** 2)), 4)
        calibration_bins = _compute_calibration_bins(y_true, y_score)
        if len(np.unique(y_true)) == 2:
            pr_auc = round(float(average_precision_score(y_true, y_score)), 4)
        else:
            pr_auc = None
    else:
        brier_score = None
        calibration_bins = []
        pr_auc = None

    biomes = sorted({str(ev.get("biome", "unknown")) for ev in evaluable})
    by_biome: Dict[str, Dict[str, Any]] = {}
    for b in biomes:
        b_rows = [ev for ev in evaluable if str(ev.get("biome", "unknown")) == b]
        b_pos = [ev for ev in b_rows if bool(ev.get("is_positive_site"))]
        b_neg = [ev for ev in b_rows if not bool(ev.get("is_positive_site"))]
        b_tp = sum(1 for ev in b_pos if bool(ev.get("detected")))
        b_fp = sum(1 for ev in b_neg if bool(ev.get("detected")))
        b_scores = np.array(
            [
                float(np.clip(ev.get("score", ev.get("prob", 1.0 if ev.get("detected") else 0.0)), 0.0, 1.0))
                for ev in b_rows
            ],
            dtype=float,
        )
        b_y = np.array([1 if ev.get("is_positive_site") else 0 for ev in b_rows], dtype=float)
        by_biome[b] = {
            "total_evaluable": len(b_rows),
            "positives_evaluable": len(b_pos),
            "tp": b_tp,
            "fp": b_fp,
            "site_recall": round(b_tp / len(b_pos), 4) if b_pos else None,
            "site_recall_ci95": _wilson_ci95(b_tp, len(b_pos)),
            "brier_score": round(float(np.mean((b_scores - b_y) ** 2)), 4) if len(b_rows) else None,
        }

    return {
        "evaluation_validity_scope": validity_scope,
        "unverified_evidence_tiers_present": unverified_present,
        "evaluable_count": len(evaluable),
        "excluded_undetectable_sites": len(excluded_undetectable),
        "tp": tp,
        "fn": fn,
        "fp": fp,
        "tn": tn,
        "site_recall": site_recall,
        "site_recall_ci95": site_recall_ci95,
        "precision_at_k": precision_at_k,
        "false_positives_per_km2": fp_per_km2,
        "mean_centroid_distance_m": mean_centroid_dist,
        "mean_spatial_iou": mean_spatial_iou,
        "pr_auc": pr_auc,
        "brier_score": brier_score,
        "calibration_bins": calibration_bins,
        "by_biome": by_biome,
    }


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _infer_zone_from_composite_path(composite_path: str, candidate_id: str) -> str:
    stem = Path(composite_path).name if composite_path else ""
    if "synthetic_posgar_faja2_dtm" in stem:
        return "SYNTHETIC_TEST"
    if "highres_san_juan_uav" in stem:
        return "HIGHRES_SAN_JUAN_UAV"
    if "highres_zenodo_3383227" in stem:
        return "HIGHRES_ZENODO_3383227"
    if "_ARQ" in stem:
        prefix = stem.split("_ARQ", 1)[0].upper()
        return prefix
    return f"ZONE_FROM_{candidate_id.rsplit('-', 1)[0]}"


def _resolve_biome_for_zone(zone_key: str, target_zones: Dict[str, Dict[str, Any]]) -> str:
    meta = target_zones.get(zone_key, {})
    if meta.get("biome"):
        return str(meta["biome"])
    return _ZONE_BIOME_FALLBACK.get(zone_key, "noa_quebradas_valles")


def _resolve_dem_resolution_for_zone(zone_key: str) -> float:
    if zone_key == "HIGHRES_SAN_JUAN_UAV":
        return 0.25
    if zone_key == "HIGHRES_ZENODO_3383227":
        return 0.50
    return 30.0


def build_curated_benchmark_v1_dataset(
    reports_dir: Optional[Path] = None,
    data_dir: Optional[Path] = None,
    out_json_path: Optional[Path] = None,
    out_report_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Construye el dataset piloto curado `BENCHMARK_V1_DATASET.json` con procedencia auditable.

    Condiciones científicas aplicadas:
    - Los 86 registros de `INVENTARIO_GEOMORFOLOGICO.geojson` se vinculan como metadatos de su
      descarte VLM correspondiente (`linked_geoform_id`), verificando que no son observaciones
      independientes ni se duplican.
    - Los descartes de rasters sintéticos de prueba (`ARQ-0025`, `ARQ-0026`) se excluyen.
    - Los controles VLM conservan `evidence_tier="AI_REJECTED_CANDIDATE"` (`archaeo_confirmed=False`,
      `eligible_for_blind_test=False`) y no inventan categorías geomorfológicas no acreditadas.
    - Las 9 entradas de `known_sites_published.csv` se marcan como
      `evidence_tier="PUBLISHED_SITE_REFERENCE"` (`coordinate_precision_m=100.0`,
      `eligible_for_blind_test=False`).
    - Al no haber aún bloques independientes `EXPERT_REVIEWED`/`FIELD_CONFIRMED`, `blind_test`
      permanece vacío (`0` entradas).
    """
    from src.config import PROJECT_ROOT, settings
    from src.core.data_fetcher import TARGET_ZONES, resolve_zone_key

    rep_dir = Path(reports_dir) if reports_dir else settings.reports_dir
    d_dir = Path(data_dir) if data_dir else (PROJECT_ROOT / "data")
    rep_dir.mkdir(parents=True, exist_ok=True)

    descartes_path = rep_dir / "DESCARTES_VLM.json"
    inventory_path = rep_dir / "INVENTARIO_GEOMORFOLOGICO.geojson"
    known_csv_path = d_dir / "known_sites_published.csv"

    source_hashes: Dict[str, Dict[str, Any]] = {}
    for label, p in (
        ("descartes_vlm", descartes_path),
        ("inventario_geomorfologico", inventory_path),
        ("known_sites_published", known_csv_path),
    ):
        if p.exists():
            source_hashes[label] = {
                "path": str(p.relative_to(d_dir.parent)) if d_dir.parent in p.parents else p.name,
                "sha256": _sha256_file(p),
                "size_bytes": p.stat().st_size,
            }

    desc_raw = json.loads(descartes_path.read_text(encoding="utf-8")).get("discarded", {})
    inv_features = (
        json.loads(inventory_path.read_text(encoding="utf-8")).get("features", [])
        if inventory_path.exists()
        else []
    )
    inv_by_id: Dict[str, Dict[str, Any]] = {
        str(f.get("properties", {}).get("id") or f.get("id")): f.get("properties", {})
        for f in inv_features
        if (f.get("properties", {}).get("id") or f.get("id"))
    }

    desc_ids = set(desc_raw.keys())
    inv_ids = set(inv_by_id.keys())
    inventory_is_strict_subset = inv_ids.issubset(desc_ids)

    raw_entries: List[BenchmarkEntry] = []
    excluded_synthetic: List[Dict[str, str]] = []

    for cid, d_obj in sorted(desc_raw.items()):
        raw_zone = _infer_zone_from_composite_path(str(d_obj.get("composite_image_path", "")), cid)
        if raw_zone == "SYNTHETIC_TEST":
            excluded_synthetic.append(
                {
                    "entry_id": cid,
                    "reason": "Proviene de raster sintético de prueba (synthetic_posgar_faja2_dtm)",
                }
            )
            continue

        canonical_zone = resolve_zone_key(raw_zone)
        biome = _resolve_biome_for_zone(canonical_zone, TARGET_ZONES)
        dem_res = _resolve_dem_resolution_for_zone(canonical_zone)
        area_m2 = float(d_obj.get("area_m2") or 1.0)
        verdict_obj = d_obj.get("vlm_verdict") or {}
        verdict = str(verdict_obj.get("verdict") or "NATURAL")

        inv_props = inv_by_id.get(cid)
        geomorph_sub = str(inv_props.get("geomorph_subtype")) if inv_props and inv_props.get("geomorph_subtype") else None

        if verdict == "ARTEFACTO":
            neg_cat: HardNegativeCategory = "artefacto_dem_interpolacion"
        elif geomorph_sub and geomorph_sub in _GEOMORPH_CONSERVATIVE_MAP:
            neg_cat = _GEOMORPH_CONSERVATIVE_MAP[geomorph_sub]
        else:
            neg_cat = "geoforma_no_especificada"

        raw_entries.append(
            BenchmarkEntry(
                entry_id=cid,
                region_block_id=f"BLK_{canonical_zone}",
                biome=biome,
                is_positive_site=False,
                archaeo_confirmed=False,
                evidence_tier="AI_REJECTED_CANDIDATE",
                source_origin="DESCARTES_VLM.json"
                + ("+INVENTARIO_GEOMORFOLOGICO.geojson" if inv_props else ""),
                linked_geoform_id=cid if inv_props else None,
                geomorph_subtype=geomorph_sub,
                eligible_for_blind_test=False,
                negative_category=neg_cat,
                dem_resolution_m=dem_res,
                expected_feature_area_m2=area_m2,
                notes=(
                    f"Control negativo candidato descartado por VLM ({verdict}, "
                    f"subtipo='{geomorph_sub or 'no_registrado'}'). No equivale a verdad de campo."
                ),
            )
        )

    published_count = 0
    if known_csv_path.exists():
        with known_csv_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for idx, row in enumerate(reader, start=1):
                published_count += 1
                z_raw = str(row.get("zone_id") or "GENERAL").strip()
                canonical_zone = resolve_zone_key(z_raw)
                biome = _resolve_biome_for_zone(canonical_zone, TARGET_ZONES)
                site_type = str(row.get("site_type") or "").strip().lower()
                # Huella macro nominal conservadora (no medida en archivo) para distinguir complejos monumentales de loci acotados
                is_localized_locus = site_type in {"arte_rupestre", "sitio_de_caza_patagonico"}
                nominal_area_m2 = 900.0 if is_localized_locus else 10000.0
                entry_id = f"PUB-{idx:03d}-{canonical_zone[:10]}"

                raw_entries.append(
                    BenchmarkEntry(
                        entry_id=entry_id,
                        region_block_id=f"BLK_{canonical_zone}",
                        biome=biome,
                        is_positive_site=True,
                        archaeo_confirmed=False,
                        evidence_tier="PUBLISHED_SITE_REFERENCE",
                        source_origin="known_sites_published.csv",
                        coordinate_precision_m=100.0,
                        eligible_for_blind_test=False,
                        dem_resolution_m=30.0,
                        expected_feature_area_m2=nominal_area_m2,
                        notes=(
                            f"Referencia publicada '{row.get('name', 'N/D')}' (fuente: {row.get('source', 'N/D')}; "
                            "coordenada aproximada ±100 m; participa en el validador espacial interno). "
                            f"Área nominal de escala={nominal_area_m2:.0f} m²."
                        ),
                    )
                )

    split_entries = assign_spatial_block_splits(
        raw_entries,
        ratios=(0.60, 0.20, 0.20),
        enforce_blind_eligibility=True,
    )

    # Resumen auditado por nivel de evidencia, categoría, split y bioma
    by_tier: Dict[str, int] = defaultdict(int)
    by_split: Dict[str, int] = defaultdict(int)
    by_neg_cat: Dict[str, int] = defaultdict(int)
    by_biome: Dict[str, int] = defaultdict(int)
    linked_geoforms_count = 0

    for e in split_entries:
        by_tier[e.evidence_tier] += 1
        by_split[e.split or "unassigned"] += 1
        by_biome[e.biome] += 1
        if e.negative_category:
            by_neg_cat[e.negative_category] += 1
        if e.linked_geoform_id:
            linked_geoforms_count += 1

    dataset_payload: Dict[str, Any] = {
        "schema_version": "benchmark-v1.0-curated-pilot",
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "scientific_status": (
            "PILOT_CONTROLS_AND_PUBLISHED_REFERENCES_ONLY — "
            "NO contiene todavía verdad arqueológica verificada en campo (FIELD_CONFIRMED=0) "
            "ni blind_test independiente."
        ),
        "source_provenance": source_hashes,
        "curation_audit": {
            "raw_descartes_count": len(desc_raw),
            "inventory_features_count": len(inv_by_id),
            "inventory_strict_subset_of_descartes": inventory_is_strict_subset,
            "linked_geoforms_merged_without_duplication": linked_geoforms_count,
            "excluded_synthetic_records": excluded_synthetic,
            "published_references_count": published_count,
            "active_curated_entries_count": len(split_entries),
            "counts_by_evidence_tier": dict(sorted(by_tier.items())),
            "counts_by_split": {
                "development": by_split.get("development", 0),
                "validation": by_split.get("validation", 0),
                "blind_test": by_split.get("blind_test", 0),
            },
            "counts_by_negative_category": dict(sorted(by_neg_cat.items())),
            "counts_by_biome": dict(sorted(by_biome.items())),
        },
        "entries": [e.model_dump() for e in split_entries],
    }

    json_out = Path(out_json_path) if out_json_path else (rep_dir / "BENCHMARK_V1_DATASET.json")
    json_out.write_text(json.dumps(dataset_payload, indent=2, ensure_ascii=False), encoding="utf-8")

    md_out = Path(out_report_path) if out_report_path else (rep_dir / "BENCHMARK_V1_QUALITY_REPORT.md")
    audit = dataset_payload["curation_audit"]
    md_lines = [
        "# Informe de Curaduría y Calidad — BENCHMARK_V1_DATASET",
        "",
        f"*Generado (UTC):* `{dataset_payload['generated_at_utc']}`",
        "",
        "> **Advertencia Epistémica:** Este benchmark piloto consolida controles negativos generados por el Juez VLM (`AI_REJECTED_CANDIDATE`) y referencias publicadas aproximadas ±100 m (`PUBLISHED_SITE_REFERENCE`). **No equivale** a ground truth arqueológico de campo ni habilita aún un `blind_test` independiente.",
        "",
        "## 1. Integridad y No-Duplicación de Fuentes",
        "",
        f"- **Descartes VLM de entrada (`DESCARTES_VLM.json`):** {audit['raw_descartes_count']}",
        f"- **Inventario Geomorfológico (`INVENTARIO_GEOMORFOLOGICO.geojson`):** {audit['inventory_features_count']} registros — subconjunto estricto de descartes: `{audit['inventory_strict_subset_of_descartes']}` (fusionados como atributos en {audit['linked_geoforms_merged_without_duplication']} entradas sin duplicar observaciones).",
        f"- **Registros sintéticos excluidos:** {len(excluded_synthetic)} ({', '.join(x['entry_id'] for x in excluded_synthetic) or 'ninguno'})",
        f"- **Referencias publicadas (`known_sites_published.csv`):** {published_count} (±100 m, excluidas de `blind_test`)",
        f"- **Total activo en `BENCHMARK_V1_DATASET.json`:** **{audit['active_curated_entries_count']} entradas**",
        "",
        "## 2. Hashes SHA-256 de Procedencia",
        "",
        "| Fuente | SHA-256 | Tamaño (bytes) |",
        "| :--- | :--- | :---: |",
    ]
    for src_name, src_info in source_hashes.items():
        md_lines.append(f"| `{src_name}` | `{src_info['sha256']}` | {src_info['size_bytes']} |")
    md_lines += [
        "",
        "## 3. Distribución por Nivel de Evidencia y Partición Espacial",
        "",
        "| Nivel de Evidencia | Cantidad | `archaeo_confirmed` | Elegible `blind_test` |",
        "| :--- | :---: | :---: | :---: |",
        f"| `AI_REJECTED_CANDIDATE` | {by_tier.get('AI_REJECTED_CANDIDATE', 0)} | `False` | `False` |",
        f"| `PUBLISHED_SITE_REFERENCE` | {by_tier.get('PUBLISHED_SITE_REFERENCE', 0)} | `False` | `False` |",
        f"| `EXPERT_REVIEWED` | {by_tier.get('EXPERT_REVIEWED', 0)} | `True` (cuando aplique) | `True` |",
        f"| `FIELD_CONFIRMED` | {by_tier.get('FIELD_CONFIRMED', 0)} | `True` | `True` |",
        "",
        "### Partición por Bloques Espaciales (Roberts et al. 2017)",
        f"- `development`: **{audit['counts_by_split']['development']}**",
        f"- `validation`: **{audit['counts_by_split']['validation']}**",
        f"- `blind_test`: **{audit['counts_by_split']['blind_test']}** (reservado exclusivamente para muestras independientes futuras con `eligible_for_blind_test=True`)",
        "",
        "### Categorías Conservadoras de Negativos",
        "",
    ]
    for cat, cnt in audit["counts_by_negative_category"].items():
        md_lines.append(f"- `{cat}`: {cnt}")

    md_out.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    return {
        "dataset_json_path": str(json_out),
        "quality_report_path": str(md_out),
        "curation_audit": audit,
        "source_provenance": source_hashes,
    }
