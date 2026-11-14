"""Etapa 0 — Manifiesto reproducible, fuente única de verdad y estados formales de evidencia."""

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.config import PROJECT_ROOT, settings
from src.schemas import CandidateLifecycleState

CLAIMS_REGISTRY: Dict[str, List[str]] = {
    "supported_claims": [
        "Ingesta geodésica reproducible por bloques HTTP Range Request y reproyección automática a POSGAR 2007 (EPSG:5343–5349).",
        "Detección algorítmica de anomalías microtopográficas positivas y negativas mediante SLRM NaN-safe, Pendiente, SVF/Openness y segmentación morfométrica con piso físico de 2 píxeles nativos.",
        "Filtrado multifuente contra catastro público (IGN WFS, OpenStreetMap Overpass) y catálogo de sitios publicados (±100 m).",
        "Inspección visual multimodal de hasta 6 paneles (DTM/SLRM/Perfil/Blender 3D + Sentinel-2 RGB/NDVI) y trazabilidad forense de descartes e inventario geomorfológico.",
        "Resguardo estricto de coordenadas sensibles conforme a la Ley Nacional N° 25.743 (ANEXO confidencial y exclusión GeoJSON en Git).",
    ],
    "unsupported_claims": [
        "Descubrimiento automático o confirmación de sitios arqueológicos sin inspección de campo autorizada y dictamen de especialista.",
        "Detección de muros finos, casas-pozo o micro-estructuras (< ~1800 m²) sobre DEM satelitales globales de 30 m/px.",
        "Interpretación directa del score morfológico o ML como probabilidad arqueológica calibrada sin benchmark real independiente ni evaluación en terreno.",
        "Detección automática de saqueo (huaqueo) como acusación legal autónoma sin verificación técnica e institucional competente.",
    ],
}


def map_verdict_to_lifecycle_state(
    verdict: Optional[str],
    classification: Optional[str] = None,
    expert_reviewed: bool = False,
    field_confirmed: bool = False,
) -> CandidateLifecycleState:
    """Separa formalmente la detección algorítmica de la evaluación IA, revisión experta y campo."""
    if field_confirmed:
        return "FIELD_CONFIRMED"
    if classification == "FALSO_POSITIVO_MODERNO" or verdict == "ARTEFACTO":
        return "REJECTED_MODERN"
    if verdict == "NATURAL":
        return "REJECTED_NATURAL"
    if expert_reviewed:
        return "EXPERT_REVIEWED"
    if verdict in {"ANTROPICA", "PENDIENTE_REVISION", "ARQUEOLOGICO"}:
        return "AI_PREASSESSMENT"
    if verdict in {"DUDOSO", "INCONCLUSIVE"}:
        return "INCONCLUSIVE"
    return "ALGORITHMIC_DETECTION"


def _git_metadata() -> Dict[str, str]:
    """Obtiene commit y tag actual de Git para reproducibilidad."""
    repo_root = PROJECT_ROOT.parent
    commit = "unknown"
    tag = "untagged"
    try:
        commit = (
            subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=repo_root,
                stderr=subprocess.DEVNULL,
                text=True,
            ).strip()
            or "unknown"
        )
    except Exception:
        pass
    try:
        tag = (
            subprocess.check_output(
                ["git", "describe", "--tags", "--exact-match"],
                cwd=repo_root,
                stderr=subprocess.DEVNULL,
                text=True,
            ).strip()
            or "untagged"
        )
    except Exception:
        pass
    return {"git_commit": commit, "git_tag": tag}


def consolidate_campaign_manifest(
    reports_dir: Optional[Path] = None,
    out_json_path: Optional[Path] = None,
    out_md_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Genera una única fuente de verdad (`CAMPAIGN_MANIFEST.json` y `BASELINE_REPORT_V1.md`)."""
    from src.core.data_fetcher import TARGET_ZONES

    rep_dir = Path(reports_dir) if reports_dir else settings.reports_dir
    rep_dir.mkdir(parents=True, exist_ok=True)
    json_path = Path(out_json_path) if out_json_path else (rep_dir / "CAMPAIGN_MANIFEST.json")
    md_path = Path(out_md_path) if out_md_path else (rep_dir / "BASELINE_REPORT_V1.md")

    state_counts: Dict[str, int] = {
        "ALGORITHMIC_DETECTION": 0,
        "AI_PREASSESSMENT": 0,
        "EXPERT_REVIEWED": 0,
        "FIELD_CONFIRMED": 0,
        "REJECTED_NATURAL": 0,
        "REJECTED_MODERN": 0,
        "INCONCLUSIVE": 0,
    }

    descartes_path = rep_dir / "DESCARTES_VLM.json"
    descartes_map: Dict[str, Any] = {}
    if descartes_path.exists():
        try:
            loaded = json.loads(descartes_path.read_text(encoding="utf-8"))
            descartes_map = loaded.get("discarded", {}) or {}
        except Exception:
            descartes_map = {}

    for entry in descartes_map.values():
        v_obj = entry.get("vlm_verdict") or {}
        st = map_verdict_to_lifecycle_state(v_obj.get("verdict"))
        state_counts[st] = state_counts.get(st, 0) + 1

    mapa_final_path = rep_dir / "MAPA_FINAL_PROSPECCION.geojson"
    final_features: List[Dict[str, Any]] = []
    if mapa_final_path.exists():
        try:
            final_fc = json.loads(mapa_final_path.read_text(encoding="utf-8"))
            final_features = final_fc.get("features", []) or []
        except Exception:
            final_features = []

    for feat in final_features:
        props = feat.get("properties") or {}
        v_obj = props.get("vlm_verdict") or {}
        st = map_verdict_to_lifecycle_state(
            verdict=v_obj.get("verdict"),
            classification=props.get("classification"),
            expert_reviewed=bool(props.get("expert_reviewed", False)),
            field_confirmed=bool(props.get("field_confirmed", False)),
        )
        state_counts[st] = state_counts.get(st, 0) + 1

    geoforms_count = 0
    inv_path = rep_dir / "INVENTARIO_GEOMORFOLOGICO.geojson"
    if inv_path.exists():
        try:
            inv_fc = json.loads(inv_path.read_text(encoding="utf-8"))
            geoforms_count = len(inv_fc.get("features", []) or [])
        except Exception:
            geoforms_count = 0

    zone_manifests: List[Dict[str, Any]] = []
    for zkey, zmeta in TARGET_ZONES.items():
        bbox = zmeta.get("bbox", [])
        zone_manifests.append(
            {
                "zone_key": zkey,
                "name": zmeta.get("name"),
                "biome": zmeta.get("biome"),
                "bbox_wgs84": bbox,
                "epsg_posgar2007": zmeta.get("epsg"),
                "datum": "POSGAR 2007",
                "preferred_dem": zmeta.get("preferred_dem", "copernicus_aws"),
                "algorithm_params": {
                    "slrm_radius_m": zmeta.get("slrm_radius_m"),
                    "min_area_m2": zmeta.get("min_area_m2"),
                    "max_area_m2": zmeta.get("max_area_m2"),
                    "min_dz_m": zmeta.get("min_dz_m"),
                    "max_slope_deg": zmeta.get("max_slope_deg"),
                },
            }
        )

    git_meta = _git_metadata()
    manifest: Dict[str, Any] = {
        "schema_version": "baseline-v1.0",
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "code_provenance": git_meta,
        "runtime_config": {
            "dem_provider": settings.dem_provider,
            "dem_fallback_chain": list(settings.dem_fallback_chain),
            "optical_provider": settings.optical_provider,
            "max_master_side_px": settings.max_master_side_px,
            "max_optical_chip_px": settings.max_optical_chip_px,
            "optical_buffer_m": settings.optical_buffer_m,
        },
        "summary": {
            "catalog_zones_count": len(zone_manifests),
            "discarded_total": len(descartes_map),
            "active_final_map_count": len(final_features),
            "geoforms_inventory_count": geoforms_count,
            "lifecycle_state_counts": state_counts,
        },
        "claims_registry": CLAIMS_REGISTRY,
        "zones": zone_manifests,
    }

    json_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    md_lines: List[str] = [
        "# Informe de Línea de Base Reproducible — ArchaeoLiDAR-AR",
        "",
        f"*Generado (UTC):* `{manifest['generated_at_utc']}` | *Commit Git:* `{git_meta['git_commit']}` | *Tag:* `{git_meta['git_tag']}`",
        "",
        "## 1. Resumen Único de Campaña (Fuente Única de Verdad)",
        "",
        f"- **Zonas en catálogo:** {len(zone_manifests)}",
        f"- **Candidatos activos en `MAPA_FINAL_PROSPECCION.geojson`:** {len(final_features)}",
        f"- **Descartes archivados (`DESCARTES_VLM.json`):** {len(descartes_map)}",
        f"- **Geoformas catalogadas (`INVENTARIO_GEOMORFOLOGICO.geojson`):** {geoforms_count}",
        "",
        "### Conteo por Estado Formal de Evidencia",
        "",
        "| Estado | Significado | Cantidad |",
        "| :--- | :--- | :---: |",
        f"| `ALGORITHMIC_DETECTION` | Anomalía topográfica detectada por algoritmo | {state_counts['ALGORITHMIC_DETECTION']} |",
        f"| `AI_PREASSESSMENT` | Evaluación preliminar ML / VLM | {state_counts['AI_PREASSESSMENT']} |",
        f"| `EXPERT_REVIEWED` | Revisado por especialista humano | {state_counts['EXPERT_REVIEWED']} |",
        f"| `FIELD_CONFIRMED` | Verificado en campo con autorización | {state_counts['FIELD_CONFIRMED']} |",
        f"| `REJECTED_NATURAL` | Descartado como geoforma natural | {state_counts['REJECTED_NATURAL']} |",
        f"| `REJECTED_MODERN` | Descartado como infraestructura moderna o artefacto | {state_counts['REJECTED_MODERN']} |",
        f"| `INCONCLUSIVE` | Evidencia insuficiente a la resolución disponible | {state_counts['INCONCLUSIVE']} |",
        "",
        "## 2. Registro de Afirmaciones (Alcance Científico Honesto)",
        "",
        "### Lo que el proyecto SÍ puede afirmar actualmente",
        *[f"- {c}" for c in CLAIMS_REGISTRY["supported_claims"]],
        "",
        "### Lo que el proyecto NO afirma sin validación externa",
        *[f"- {c}" for c in CLAIMS_REGISTRY["unsupported_claims"]],
        "",
        "---",
        "*Manifiesto JSON estructurado:* `data/reports/CAMPAIGN_MANIFEST.json`",
        "",
    ]
    md_path.write_text("\n".join(md_lines), encoding="utf-8")
    manifest["manifest_json_path"] = str(json_path)
    manifest["baseline_report_md_path"] = str(md_path)
    return manifest
