#!/usr/bin/env python3
"""Regenera todos los dossiers INAPL con el template vigente (Conclusión Ejecutiva + imágenes embebidas).

Uso:
    python scripts/regenerate_dossiers.py [reports_dir]

Recorre `data/reports/` y regenera el dossier de cada candidato a partir de:
1. `DESCARTES_VLM.json` (descartes auditados: NATURAL/ARTEFACTO con dictamen completo).
2. `MAPA_FINAL_PROSPECCION.geojson` (confirmados / pendientes).
3. Dossiers huérfanos existentes en disco (p. ej. corridas anteriores sin registro en
   los archivos anteriores): se reconstruyen con props mínimas y estado
   PENDIENTE_REVISION, tomando el centroide del ANEXO confidencial si está disponible.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.report_generator import generate_inapl_dossier  # noqa: E402


def _load_props_index(reports_dir: Path) -> dict:
    """Índice id -> props completas desde los mapas por zona y el mapa final."""
    index: dict = {}
    for map_path in sorted(reports_dir.glob("MAPA_PROSPECCION_*.geojson")) + [
        reports_dir / "MAPA_FINAL_PROSPECCION.geojson"
    ]:
        if not map_path.exists():
            continue
        try:
            fc = json.loads(map_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        for feat in fc.get("features", []):
            fid = feat.get("id") or feat.get("properties", {}).get("id")
            if fid and fid not in index:
                props = dict(feat.get("properties", {}))
                if feat.get("geometry"):
                    props.setdefault("geometry_geojson", feat["geometry"])
                index[fid] = props
    return index


def _load_annex_centroids(reports_dir: Path) -> dict:
    """Índice id -> centroid WGS84 desde el ANEXO confidencial (fallback para huérfanos)."""
    annex = reports_dir / "ANEXO_CONFIDENCIAL_COORDENADAS.json"
    if not annex.exists():
        return {}
    try:
        data = json.loads(annex.read_text(encoding="utf-8"))
        return {
            cid: rec.get("centroid_wgs84")
            for cid, rec in (data.get("candidates") or {}).items()
            if rec.get("centroid_wgs84")
        }
    except Exception:
        return {}


def regenerate(reports_dir: Path) -> dict:
    desc_path = reports_dir / "DESCARTES_VLM.json"
    desc = {}
    if desc_path.exists():
        desc = json.loads(desc_path.read_text(encoding="utf-8")).get("discarded", {})

    final_path = reports_dir / "MAPA_FINAL_PROSPECCION.geojson"
    final_feats = []
    if final_path.exists():
        try:
            final_feats = json.loads(final_path.read_text(encoding="utf-8")).get("features", [])
        except Exception:
            pass

    props_index = _load_props_index(reports_dir)
    annex_centroids = _load_annex_centroids(reports_dir)

    regenerated: list = []
    seen: set = set()

    # 1. Descartes auditados (dictamen completo disponible)
    for cid, entry in desc.items():
        verdict = entry.get("vlm_verdict") or {}
        props = props_index.get(cid) or {k: entry.get(k) for k in ("area_m2", "mean_elevation_m", "anomaly_type")}
        props = dict(props)
        props.setdefault("id", cid)
        props.setdefault("centroid_wgs84", annex_centroids.get(cid))
        payload = {**props, "id": cid, "vlm_verdict": verdict}
        generate_inapl_dossier(payload, out_dir=reports_dir)
        regenerated.append(cid)
        seen.add(cid)

    # 2. Confirmados / pendientes del mapa final
    for feat in final_feats:
        fid = feat.get("id") or feat.get("properties", {}).get("id")
        if not fid or fid in seen:
            continue
        props = dict(feat.get("properties", {}))
        if feat.get("geometry"):
            props.setdefault("geometry_geojson", feat["geometry"])
        props.setdefault("centroid_wgs84", annex_centroids.get(fid))
        payload = {**props, "id": fid, "vlm_verdict": feat.get("properties", {}).get("vlm_verdict")}
        generate_inapl_dossier(payload, out_dir=reports_dir)
        regenerated.append(fid)
        seen.add(fid)

    # 3. Dossiers huérfanos en disco (corridas previas sin registro en DESCARTES/MAPA_FINAL)
    for dossier_path in sorted(reports_dir.glob("DOSSIER_INAPL_*.md")):
        cid = dossier_path.stem.replace("DOSSIER_INAPL_", "")
        if cid in seen:
            continue
        payload = {
            "id": cid,
            "centroid_wgs84": annex_centroids.get(cid),
            "classification": "CANDIDATO_INEDITO",
        }
        # Recuperar área/dZ/tipología/confianza/lámina del dossier existente si se puede
        try:
            text = dossier_path.read_text(encoding="utf-8")
            for line in text.splitlines():
                if "**Área Estimada en Planta:**" in line:
                    payload["area_m2"] = line.split("`")[1].replace(" m²", "")
                elif "**Sobre-elevación Local Media (SLRM):**" in line:
                    payload["mean_elevation_m"] = line.split("`")[1].replace(" m", "")
                elif "**Tipología Morfológica**" in line:
                    payload["anomaly_type"] = line.split("`")[1]
                elif "**Índice de Confianza Algorítmica**" in line:
                    payload["confidence"] = line.split("`")[1]
                elif "**Índice de Rectangularidad:**" in line:
                    payload["rectangularity"] = line.split("`")[1]
                elif "**Índice de Circularidad Isoperimétrica:**" in line:
                    payload["circularity"] = line.split("`")[1]
                elif "**Lámina Compuesta (Hillshade" in line:
                    path_str = line.split("`")[1] if "`" in line else None
                    if path_str and path_str != "N/D" and (reports_dir.parent / path_str.replace("./", "")).exists():
                        payload["composite_image_path"] = path_str
        except Exception:
            pass
        generate_inapl_dossier(payload, out_dir=reports_dir)
        regenerated.append(cid)
        seen.add(cid)

    return {"regenerated": len(regenerated), "ids": regenerated}


def main() -> None:
    reports_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("./data/reports")
    result = regenerate(reports_dir)
    print(f"✔ Dossiers regenerados: {result['regenerated']} en {reports_dir}")


if __name__ == "__main__":
    main()
