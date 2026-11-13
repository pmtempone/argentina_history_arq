"""Etapas 2 y 3 — Diseño del Benchmark Nacional V1, partición espacial por bloques y métricas arqueológicas.

Implementa:
- Esquema `BenchmarkEntry` con clases de negativos difíciles (geoformas naturales y
  estructuras modernas) y bandera `sensor_detectable` según resolución física del DEM.
- Partición espacial por bloques (`assign_spatial_block_splits`) siguiendo Roberts et al.
  (2017), garantizando cero fuga espacial (`region_block_id` completo en un único split).
- Regla formal de abstención (`should_abstain_prediction`) cuando la escala del sensor o la
  incertidumbre del modelo no habilitan una predicción confiable.
- Cálculo de métricas orientadas a campaña de campo (`compute_benchmark_metrics`): recall
  por sitio con IC 95% de Wilson, precisión@K, falsos positivos por km², distancia media de
  centroide, IoU espacial, PR-AUC, Brier score y desglose por bioma.
"""

from __future__ import annotations

import hashlib
import math
from collections import defaultdict
from typing import Any, Dict, List, Literal, Optional, Tuple

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

SplitLiteral = Literal["development", "validation", "blind_test"]


class BenchmarkEntry(BaseModel):
    """Registro auditado del Benchmark Nacional V1 (positivos y negativos difíciles)."""

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
        description="True únicamente si fue verificado en campo o catálogo especializado revisado.",
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
) -> List[BenchmarkEntry]:
    """Asigna `development`, `validation` y `blind_test` por bloque espacial completo.

    Sigue Roberts et al. (2017): todas las entradas que comparten `region_block_id`
    se asignan al mismo split para evitar fuga por autocorrelación espacial.
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
    targets = [r * total_n for r in ratios]
    assigned_counts = [0, 0, 0]
    block_to_split: Dict[str, SplitLiteral] = {}

    if len(sorted_blocks) >= 3:
        # Siembra determinista de un bloque en cada split (mayor bloque al set de development)
        for split_idx, block_idx in zip((0, 2, 1), (0, 1, 2)):
            if block_idx < len(sorted_blocks):
                blk_id, blk_entries = sorted_blocks[block_idx]
                block_to_split[blk_id] = split_names[split_idx]
                assigned_counts[split_idx] += len(blk_entries)

        remaining = sorted_blocks[3:]
    else:
        remaining = sorted_blocks

    for blk_id, blk_entries in remaining:
        # Elegir el split con mayor déficit relativo respecto a su cuota objetivo
        deficits = [
            (targets[i] - assigned_counts[i]) / max(targets[i], 1.0) for i in range(3)
        ]
        best_split_idx = int(np.argmax(deficits))
        block_to_split[blk_id] = split_names[best_split_idx]
        assigned_counts[best_split_idx] += len(blk_entries)

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
) -> Dict[str, Any]:
    """Calcula métricas orientadas a validación arqueológica y planificación de campaña.

    Sitios positivos con `sensor_detectable=False` se contabilizan en
    `excluded_undetectable_sites` y se excluyen del cálculo de `site_recall` para no
    penalizar ni falsear métricas sobre rasgos físicamente invisibles al sensor.
    """
    if scanned_area_km2 <= 0.0:
        raise ValueError(f"scanned_area_km2 debe ser > 0, recibido: {scanned_area_km2}")

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

    # Ranking para Precision@K y curvas probabilísticas
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

    # Desglose por bioma (sin inflación global)
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
