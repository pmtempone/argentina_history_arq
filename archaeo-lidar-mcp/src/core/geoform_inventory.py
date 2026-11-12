"""Inventario geomorfológico secundario: los descartes NATURAL como insumo científico.

Cada candidato descartado como `NATURAL` por el Juez Pericial VLM es una geoforma
clasificada y verificada: paleocauces, médanos fósiles, morrenas, escarpas, vaguadas,
albardones, domos volcánicos, canchales. Este módulo los persiste en
`data/reports/INVENTARIO_GEOMORFOLOGICO.geojson` con subtipo etiquetado, para que el
trabajo de descarte sirva directamente como insumo hidrogeológico y geomorfológico.

Nota legal: los elementos del inventario son geoformas naturales SIN valor patrimonial;
sus coordenadas no están protegidas por la Ley 25.743 (que resguarda sitios arqueológicos).
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

INVENTORY_FILENAME: str = "INVENTARIO_GEOMORFOLOGICO.geojson"

# Tabla de subtipos: se evalúa en orden de especificidad; la primera coincidencia gana
SUBTYPE_KEYWORDS: List[Tuple[str, List[str]]] = [
    ("paleocauce", ["paleocauce", "cauce", "escorrent", "cárcava", "canal", "vaguada", "cárcava"]),
    ("medano_fosil", ["médano", "medano", "duna", "eólico", "eolico", "arenoso", "banco arenoso"]),
    ("morrena", ["morrena", "glacial", "nival", "periglacial", "nivación", "nivacion"]),
    ("cono_aluvial", ["cono de deyección", "cono aluvial", "abanico aluvial", "abanico", "dorso aluvial"]),
    ("escarpa", ["escarpa", "falla", "banco estratigr", "estratigr", "farallón", "farallon", "dique", "ruptura superficial"]),
    ("roca_fracturada", ["diaclasado", "fracturado", "roca madre", "afloramiento", "erosión diferencial", "erosion diferencial"]),
    ("domo_volcanico", ["volcán", "volcan", "basált", "basalt", "lava", "ignimbri", "caldera", "escoria", "cráter", "crater", "toba"]),
    ("canchal", ["canchal", "derrubio", "coluvial", "colapso", "bloque errático", "bloque rocoso"]),
    ("albardon", ["albardón", "albardon", "cordón", "cordon", "espolón", "espolon", "spit", "costera"]),
    ("lomada", ["lomada", "prominencia", "promontorio", "interfluvio", "hombro", "morro", "cerrito", "domo redondeado", "ondulación", "ondulacion", "cresta orográfica", "cresta orografica"]),
]


def classify_geoform_subtype(functional_interpretation: str) -> str:
    """Mapea la interpretación funcional del Juez VLM a un subtipo geomorfológico."""
    text = (functional_interpretation or "").lower()
    for subtype, keywords in SUBTYPE_KEYWORDS:
        if any(kw in text for kw in keywords):
            return subtype
    return "geoforma_no_clasificada"


def append_geoform_inventory(
    candidate_id: str,
    props: Dict[str, Any],
    verdict_data: Dict[str, Any],
    reports_dir: Optional[Union[str, Path]] = None,
) -> Optional[str]:
    """Agrega un candidato `NATURAL` al inventario geomorfológico (GeoJSON).

    Args:
        candidate_id: ID del candidato descartado.
        props: Propiedades del candidato (area, tipo, centroide, etc.).
        verdict_data: Dictamen pericial (debe tener verdict == "NATURAL").
        reports_dir: Directorio de reportes (por defecto `settings.reports_dir`).

    Returns:
        Ruta del inventario actualizado, o None si el veredicto no es NATURAL.
    """
    if str(verdict_data.get("verdict", "")).upper() != "NATURAL":
        return None

    rep_dir = Path(reports_dir) if reports_dir else Path("./data/reports")
    rep_dir.mkdir(parents=True, exist_ok=True)
    inventory_path = rep_dir / INVENTORY_FILENAME

    if inventory_path.exists():
        try:
            fc = json.loads(inventory_path.read_text(encoding="utf-8"))
        except Exception:
            fc = {"type": "FeatureCollection", "features": []}
    else:
        fc = {"type": "FeatureCollection", "features": []}

    centroid = props.get("centroid_wgs84")
    if not centroid or len(centroid) != 2:
        return None

    subtype = classify_geoform_subtype(str(verdict_data.get("functional_interpretation", "")))
    feature = {
        "type": "Feature",
        "id": candidate_id,
        "geometry": {"type": "Point", "coordinates": [round(float(centroid[0]), 6), round(float(centroid[1]), 6)]},
        "properties": {
            "id": candidate_id,
            "geomorph_subtype": subtype,
            "anomaly_type": props.get("anomaly_type"),
            "area_m2": props.get("area_m2"),
            "mean_elevation_m": props.get("mean_elevation_m"),
            "verdict": "NATURAL",
            "certainty_pct": verdict_data.get("certainty_pct"),
            "functional_interpretation": verdict_data.get("functional_interpretation"),
            "backend": verdict_data.get("backend"),
            "recorded_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "note": "Inventario geomorfológico derivado de descartes del Juez Pericial VLM (geoformas naturales, no patrimoniales).",
        },
    }
    fc["features"].append(feature)
    fc.setdefault("metadata", {})["last_updated_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    fc["metadata"]["feature_count"] = len(fc["features"])
    inventory_path.write_text(json.dumps(fc, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(inventory_path)


def backfill_inventory_from_descartes(
    reports_dir: Optional[Union[str, Path]] = None,
) -> str:
    """Reconstruye el inventario completo desde `DESCARTES_VLM.json` y los mapas por zona."""
    rep_dir = Path(reports_dir) if reports_dir else Path("./data/reports")
    disc_path = rep_dir / "DESCARTES_VLM.json"
    if not disc_path.exists():
        raise FileNotFoundError(f"No existe {disc_path}")

    desc = json.loads(disc_path.read_text(encoding="utf-8")).get("discarded", {})
    # Props completas por id desde los mapas por zona
    id_props: Dict[str, Dict[str, Any]] = {}
    for map_path in sorted(rep_dir.glob("MAPA_PROSPECCION_*.geojson")):
        try:
            fc = json.loads(map_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        for feat in fc.get("features", []):
            fid = feat.get("id") or feat.get("properties", {}).get("id")
            if fid:
                id_props[fid] = feat.get("properties", {})

    # Reiniciar el inventario para un backfill determinístico
    inventory_path = rep_dir / INVENTORY_FILENAME
    if inventory_path.exists():
        inventory_path.unlink()

    count = 0
    for cid, entry in desc.items():
        verdict = entry.get("vlm_verdict", {})
        if str(verdict.get("verdict", "")).upper() != "NATURAL":
            continue
        props = dict(id_props.get(cid) or {k: entry.get(k) for k in ("area_m2", "mean_elevation_m", "anomaly_type")})
        if "centroid_wgs84" not in props:
            continue
        append_geoform_inventory(cid, props, verdict, reports_dir=rep_dir)
        count += 1
    return str(inventory_path)
