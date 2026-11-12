"""Juez pericial multimodal (VLM) para láminas compuestas de candidatos arqueológicos.

Backends (Opción C):
1. ``gemini``: si existe ``GEMINI_API_KEY`` y el SDK ``google-genai`` está instalado.
2. ``mcp_host``: el agente anfitrión inspecciona la imagen vía ``tool_vlm_judge_candidate`` y registra
   su dictamen con ``tool_record_vlm_verdict``.
3. Sin backend: ``PENDIENTE_REVISION`` con certeza 0 (nunca se inventa un veredicto).
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

from src.config import settings
from src.core.geoform_inventory import append_geoform_inventory
from src.core.report_generator import generate_inapl_dossier

VerdictLiteral = Literal["ANTROPICA", "NATURAL", "ARTEFACTO", "PENDIENTE_REVISION"]
DISCARD_VERDICTS = {"NATURAL", "ARTEFACTO"}

ARCHAEO_SYSTEM_PROMPT = """Actuás como un Arqueólogo Espacial Senior del CONICET especialista en el Noroeste Argentino.
Analizá los 4 paneles de la lámina adjunta (1: Hillshade 1.5x, 2: SLRM microtopográfico, 3: Perfil de corte 2D, 4: Render 3D isométrico; si la lámina es de una campaña previa puede tener 3 paneles sin render).
Tu objetivo es determinar si la estructura es:
a) ESTRUCTURA_ANTROPICA_PROBABLE (Muro pircado, recinto, andén, corral).
b) FORMACION_GEOLOGICA_NATURAL (Filo rocoso, dique ígneo, escarpa de falla).
c) ARTEFACTO_DIGITAL (Ruido de interpolación del DEM).

Respondé en formato estructurado:
- Veredicto final: (ANTROPICA / NATURAL / ARTEFACTO)
- Nivel de certeza (0 a 100%)
- Interpretación funcional: ¿Qué parece ser? (ej. Pucará, andenería, kancha, corral).
- Justificación geomorfológica: Explicá qué observás en el perfil 2D y en los bordes del Hillshade.
- Decisión: ¿Vale la pena una inspección terrestre o vuelo de dron? (SÍ / NO)

SI el candidato figura con `patrimonial_priority: ALERTA_SAQUEO`, priorizá el análisis de
evidencia de excavación ilegal (bordes netos, escombro perimetral, fondo irregular) y
recomendá siempre la notificación al INAPL en la interpretación funcional.
"""


class VLMVerdict(BaseModel):
    """Dictamen pericial estructurado emitido por el modelo multimodal o el agente anfitrión."""

    model_config = ConfigDict(extra="forbid")

    verdict: VerdictLiteral = Field(..., description="ANTROPICA, NATURAL, ARTEFACTO o PENDIENTE_REVISION.")
    certainty_pct: int = Field(..., ge=0, le=100, description="Nivel de certeza 0-100%.")
    functional_interpretation: str = Field(..., description="Interpretación funcional (pucará, andén, corral...).")
    geomorphological_justification: str = Field(..., description="Justificación basada en perfil 2D y bordes.")
    field_inspection_recommended: bool = Field(..., description="¿Amerita inspección terrestre o dron?")
    backend: str = Field(default="unknown", description="Backend que emitió el dictamen.")


def build_judge_prompt(candidate_id: str, metrics: Dict[str, Any]) -> str:
    """Construye el prompt pericial con las métricas cuantitativas del candidato."""
    lines = [ARCHAEO_SYSTEM_PROMPT, "", f"Candidato: {candidate_id}", "Métricas cuantitativas:"]
    for key in (
        "biome",
        "archaeo_context",
        "anomaly_type",
        "area_m2",
        "mean_elevation_m",
        "confidence",
        "ml_probability",
        "rectangularity",
        "circularity",
        "slope_mean_deg",
        "distance_to_water_m",
        "dem_source",
        "dem_native_resolution_m",
        "dem_processing_resolution_m",
        "patrimonial_priority",
        "nearest_known_site",
        "diameter_m",
    ):
        if key in metrics:
            lines.append(f"- {key}: {metrics[key]}")
    lines.append(
        "IMPORTANTE: considerá la resolución nativa del DEM; el supermuestreo no agrega detalle real."
    )
    return "\n".join(lines)


def _cache_path(candidate_id: str, cache_dir: Optional[Path] = None) -> Path:
    base = cache_dir or (settings.processed_dir / "vlm_cache")
    base.mkdir(parents=True, exist_ok=True)
    return base / f"{candidate_id}.json"


def _evaluate_with_gemini(image_path: Path, prompt: str) -> VLMVerdict:
    """Evalúa la lámina con la API de Gemini usando salida JSON estructurada."""
    from google import genai  # type: ignore[import-not-found]
    from google.genai import types  # type: ignore[import-not-found]

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    model_name = os.environ.get("GEMINI_VLM_MODEL", "gemini-2.5-flash")
    response = client.models.generate_content(
        model=model_name,
        contents=[
            types.Part.from_bytes(data=image_path.read_bytes(), mime_type="image/png"),
            prompt,
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=VLMVerdict,
            temperature=0.1,
        ),
    )
    data = json.loads(response.text)
    data["backend"] = f"gemini:{model_name}"
    return VLMVerdict.model_validate(data)


def evaluate_candidate_with_vlm(
    candidate_id: str,
    composite_image_path: Union[str, Path],
    metrics: Dict[str, Any],
    use_cache: bool = True,
    cache_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Evalúa una lámina compuesta con el backend disponible y devuelve un ``VLMVerdict`` serializado.

    Orden de resolución: caché (dictamen previo, incluido el del agente MCP) -> Gemini -> PENDIENTE_REVISION.
    """
    image = Path(composite_image_path)
    cache_file = _cache_path(candidate_id, cache_dir)

    if use_cache and cache_file.exists():
        cached = VLMVerdict.model_validate(json.loads(cache_file.read_text(encoding="utf-8")))
        if cached.verdict != "PENDIENTE_REVISION":
            return cached.model_dump()

    if not image.exists():
        raise FileNotFoundError(f"No existe la lámina compuesta: {image}")

    prompt = build_judge_prompt(candidate_id, metrics)
    verdict: VLMVerdict
    if os.environ.get("GEMINI_API_KEY"):
        try:
            verdict = _evaluate_with_gemini(image, prompt)
        except Exception as exc:  # noqa: BLE001
            verdict = VLMVerdict(
                verdict="PENDIENTE_REVISION",
                certainty_pct=0,
                functional_interpretation="Sin dictamen",
                geomorphological_justification=f"Fallo del backend Gemini: {exc}",
                field_inspection_recommended=False,
                backend="gemini_error",
            )
    else:
        verdict = VLMVerdict(
            verdict="PENDIENTE_REVISION",
            certainty_pct=0,
            functional_interpretation="Sin dictamen",
            geomorphological_justification=(
                "No hay backend multimodal configurado (GEMINI_API_KEY ausente). "
                "Requiere revisión por el agente anfitrión vía tool_vlm_judge_candidate."
            ),
            field_inspection_recommended=False,
            backend="none",
        )

    if verdict.verdict != "PENDIENTE_REVISION":
        cache_file.write_text(verdict.model_dump_json(indent=2), encoding="utf-8")
    return verdict.model_dump()


def prepare_mcp_judgement(
    candidate_id: str,
    reports_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Devuelve imagen, prompt y métricas para que el agente anfitrión actúe como perito."""
    feat = _find_feature(candidate_id, reports_dir or settings.reports_dir)
    props = feat["properties"]
    return {
        "candidate_id": candidate_id,
        "composite_image_path": props.get("composite_image_path"),
        "prompt": build_judge_prompt(candidate_id, props),
        "metrics": props,
        "response_schema": VLMVerdict.model_json_schema(),
    }


def _find_feature(candidate_id: str, reports_dir: Path) -> Dict[str, Any]:
    map_path = reports_dir / "MAPA_FINAL_PROSPECCION.geojson"
    if map_path.exists():
        fc = json.loads(map_path.read_text(encoding="utf-8"))
        for feat in fc.get("features", []):
            if feat.get("id") == candidate_id or feat.get("properties", {}).get("id") == candidate_id:
                return feat
    for p in sorted(reports_dir.glob("MAPA_PROSPECCION_*.geojson")):
        try:
            fc = json.loads(p.read_text(encoding="utf-8"))
            for feat in fc.get("features", []):
                if feat.get("id") == candidate_id or feat.get("properties", {}).get("id") == candidate_id:
                    return feat
        except Exception:
            continue
    disc_path = reports_dir / "DESCARTES_VLM.json"
    if disc_path.exists():
        try:
            disc = json.loads(disc_path.read_text(encoding="utf-8"))
            if candidate_id in disc.get("discarded", {}):
                entry = disc["discarded"][candidate_id]
                return {
                    "id": candidate_id,
                    "type": "Feature",
                    "geometry": None,
                    "properties": {
                        "id": candidate_id,
                        **entry,
                    },
                }
        except Exception:
            pass
    raise KeyError(f"Candidato {candidate_id} no encontrado en {reports_dir}")


def record_vlm_verdict(
    candidate_id: str,
    verdict_data: Dict[str, Any],
    reports_dir: Optional[Path] = None,
    cache_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Registra un dictamen: valida, cachea, regenera el dossier y filtra NATURAL/ARTEFACTO.

    Los descartes se quitan de ``MAPA_FINAL_PROSPECCION.geojson`` y se archivan en ``DESCARTES_VLM.json``.
    """
    rep_dir = reports_dir or settings.reports_dir
    verdict = VLMVerdict.model_validate(verdict_data)
    _cache_path(candidate_id, cache_dir).write_text(verdict.model_dump_json(indent=2), encoding="utf-8")

    map_path = rep_dir / "MAPA_FINAL_PROSPECCION.geojson"
    fc = json.loads(map_path.read_text(encoding="utf-8"))
    feat = _find_feature(candidate_id, rep_dir)
    props = feat["properties"]
    props["vlm_verdict"] = verdict.model_dump()

    payload: Dict[str, Any] = dict(props)
    payload["id"] = candidate_id
    payload["geometry_geojson"] = feat.get("geometry")
    payload["vlm_verdict"] = verdict.model_dump()
    dossier_path = generate_inapl_dossier(payload, out_dir=rep_dir)

    discarded = verdict.verdict in DISCARD_VERDICTS
    remaining: List[Dict[str, Any]] = []
    for f in fc.get("features", []):
        fid = f.get("id") or f.get("properties", {}).get("id")
        if fid == candidate_id:
            if not discarded:
                remaining.append(feat)
        else:
            remaining.append(f)
    fc["features"] = remaining
    fc.setdefault("metadata", {})["confirmed_inedito_count"] = len(remaining)
    map_path.write_text(json.dumps(fc, indent=2, ensure_ascii=False), encoding="utf-8")

    if discarded:
        disc_path = rep_dir / "DESCARTES_VLM.json"
        disc: Dict[str, Any] = {"discarded": {}}
        if disc_path.exists():
            disc = json.loads(disc_path.read_text(encoding="utf-8"))
        disc["updated_at_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        disc.setdefault("discarded", {})[candidate_id] = {
            "anomaly_type": props.get("anomaly_type"),
            "area_m2": props.get("area_m2"),
            "mean_elevation_m": props.get("mean_elevation_m"),
            "composite_image_path": props.get("composite_image_path"),
            "dossier_path": dossier_path,
            "vlm_verdict": verdict.model_dump(),
        }
        disc_path.write_text(json.dumps(disc, indent=2, ensure_ascii=False), encoding="utf-8")

        # Los descartes NATURAL alimentan el inventario geomorfológico secundario
        append_geoform_inventory(candidate_id, props, verdict.model_dump(), reports_dir=rep_dir)

    return {
        "candidate_id": candidate_id,
        "verdict": verdict.verdict,
        "discarded": discarded,
        "dossier_path": dossier_path,
    }
