"""Persistencia desacoplada de dictámenes periciales VLM (dossiers, GeoJSON y geoformas)."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from src.core.geoform_inventory import append_geoform_inventory
from src.core.report_generator import generate_inapl_dossier

DISCARD_VERDICTS = {"NATURAL", "ARTEFACTO"}


def find_candidate_feature(candidate_id: str, reports_dir: Path) -> Dict[str, Any]:
    """Busca el feature GeoJSON de un candidato en MAPA_FINAL, MAPA_PROSPECCION_* o DESCARTES_VLM."""
    map_path = reports_dir / "MAPA_FINAL_PROSPECCION.geojson"
    if map_path.exists():
        fc = json.loads(map_path.read_text(encoding="utf-8"))
        for feat in fc.get("features", []):
            if feat.get("id") == candidate_id or feat.get("properties", {}).get("id") == candidate_id:
                return feat
    for z_map in sorted(reports_dir.glob("MAPA_PROSPECCION_*.geojson")):
        try:
            z_fc = json.loads(z_map.read_text(encoding="utf-8"))
        except Exception:
            continue
        for feat in z_fc.get("features", []):
            if feat.get("id") == candidate_id or feat.get("properties", {}).get("id") == candidate_id:
                return feat
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
                    "properties": {"id": candidate_id, **entry},
                }
        except Exception:
            pass
    raise KeyError(f"Candidato {candidate_id} no encontrado en {reports_dir}")


def persist_verdict_artifacts(
    candidate_id: str,
    verdict_dict: Dict[str, Any],
    reports_dir: Path,
) -> Dict[str, Any]:
    """Aplica efectos secundarios en disco de un dictamen: dossier INAPL, GeoJSON, descartes e inventario."""
    map_path = reports_dir / "MAPA_FINAL_PROSPECCION.geojson"
    fc = json.loads(map_path.read_text(encoding="utf-8"))
    feat = find_candidate_feature(candidate_id, reports_dir)
    props = feat["properties"]
    props["vlm_verdict"] = verdict_dict

    payload: Dict[str, Any] = dict(props)
    payload["id"] = candidate_id
    payload["geometry_geojson"] = feat.get("geometry")
    payload["vlm_verdict"] = verdict_dict
    dossier_path = generate_inapl_dossier(payload, out_dir=reports_dir)

    discarded = verdict_dict.get("verdict") in DISCARD_VERDICTS
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

    # Purga de seguridad geodésica (Ley 25.743): quitar geometrías descartadas de MAPA_PROSPECCION_*.geojson
    if discarded:
        for z_map_path in sorted(reports_dir.glob("MAPA_PROSPECCION_*.geojson")):
            try:
                z_fc = json.loads(z_map_path.read_text(encoding="utf-8"))
                z_feats = z_fc.get("features", [])
                z_remaining = [
                    zf
                    for zf in z_feats
                    if (zf.get("id") or zf.get("properties", {}).get("id")) != candidate_id
                ]
                if len(z_remaining) != len(z_feats):
                    z_fc["features"] = z_remaining
                    z_fc.setdefault("metadata", {})["confirmed_inedito_count"] = len(z_remaining)
                    z_map_path.write_text(json.dumps(z_fc, indent=2, ensure_ascii=False), encoding="utf-8")
            except Exception:
                continue

        disc_path = reports_dir / "DESCARTES_VLM.json"
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
            "vlm_verdict": verdict_dict,
        }
        disc_path.write_text(json.dumps(disc, indent=2, ensure_ascii=False), encoding="utf-8")

        append_geoform_inventory(candidate_id, props, verdict_dict, reports_dir=reports_dir)

    return {
        "candidate_id": candidate_id,
        "verdict": verdict_dict.get("verdict"),
        "discarded": discarded,
        "dossier_path": dossier_path,
    }
