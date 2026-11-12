#!/usr/bin/env python3
"""Regenera las láminas compuestas de los candidatos auditados en formato de 4 paneles.

Las láminas generadas por versiones previas del pipeline tienen 3 paneles (el render 3D
de Blender se integró después). Este script regenera cada lámina con
`render_candidate_composite(include_3d_render=True)` reutilizando el raster maestro de su
zona, sobrescribiendo el PNG original (las rutas embebidas en los dossiers quedan válidas).

Uso:
    python scripts/regenerate_composites.py [reports_dir] [--only ID1,ID2]
"""

import argparse
import glob
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.relief_models import compute_slrm  # noqa: E402
from src.core.visual_inspector import render_candidate_composite  # noqa: E402
from pyproj import CRS, Transformer  # noqa: E402


def _resolve_masters(zone_key: str) -> tuple:
    """Localiza el DTM crudo y el SLRM maestro de la zona; computa el SLRM si falta."""
    processed = Path("./data/processed")
    raw = Path("./data/raw")
    slrm_master = processed / f"{zone_key}_master_slrm.tif"
    if not slrm_master.exists():
        dtm_glob = raw / f"{zone_key}_posgar_*.tif"
        dtm_candidates = sorted(glob.glob(str(dtm_glob)))
        if not dtm_candidates:
            dtm_candidates = sorted(glob.glob(str(raw / f"{zone_key}.tif")))
        if not dtm_candidates:
            return None, None
        compute_slrm(dtm_candidates[0], slrm_master, radius_m=15.0)
    dtm_candidates = sorted(glob.glob(str(raw / f"{zone_key}_posgar_*.tif"))) or sorted(
        glob.glob(str(raw / f"{zone_key}.tif"))
    )
    return (dtm_candidates[0] if dtm_candidates else None), slrm_master


def _zone_key_from_composite(composite_path: str) -> str:
    """Extrae la clave de zona del nombre de la lámina: '<zona>_ARQ-XXX-..._composite.png'."""
    stem = Path(composite_path).stem
    idx = stem.find("_ARQ-")
    if idx > 0:
        return stem[:idx]
    return stem.rsplit("_", 2)[0] if "_composite" in stem else stem


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reports_dir", nargs="?", default="./data/reports")
    parser.add_argument("--only", default=None, help="Lista de IDs separados por coma para regenerar solo esos candidatos.")
    args = parser.parse_args()

    reports_dir = Path(args.reports_dir)
    only = set(args.only.split(",")) if args.only else None

    desc_path = reports_dir / "DESCARTES_VLM.json"
    if not desc_path.exists():
        raise SystemExit(f"No existe {desc_path}")
    desc = json.loads(desc_path.read_text(encoding="utf-8")).get("discarded", {})

    # Centroides completos desde los mapas por zona (fallback: entry del descarte)
    props_index = {}
    for map_path in sorted(reports_dir.glob("MAPA_PROSPECCION_*.geojson")):
        try:
            fc = json.loads(map_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        for feat in fc.get("features", []):
            fid = feat.get("id") or feat.get("properties", {}).get("id")
            if fid and fid not in props_index:
                props_index[fid] = feat.get("properties", {})

    annex = reports_dir / "ANEXO_CONFIDENCIAL_COORDENADAS.json"
    annex_centroids = {}
    if annex.exists():
        data = json.loads(annex.read_text(encoding="utf-8"))
        annex_centroids = {cid: rec.get("centroid_wgs84") for cid, rec in (data.get("candidates") or {}).items()}

    ok, skipped = [], []
    for cid, entry in desc.items():
        if only and cid not in only:
            continue
        composite = entry.get("composite_image_path")
        if not composite or not Path(composite).exists():
            skipped.append((cid, "sin lámina registrada"))
            continue
        zone_key = _zone_key_from_composite(composite)
        dtm_path, slrm_path = _resolve_masters(zone_key)
        if not dtm_path or not Path(dtm_path).exists():
            skipped.append((cid, f"sin maestro para {zone_key}"))
            continue
        props = props_index.get(cid) or {}
        centroid = props.get("centroid_wgs84") or annex_centroids.get(cid)
        if not centroid:
            skipped.append((cid, "sin centroid"))
            continue

        import rasterio
        with rasterio.open(dtm_path) as src:
            epsg = src.crs.to_epsg() or 5344
        to_metric = Transformer.from_crs(CRS.from_epsg(4326), CRS.from_epsg(epsg), always_xy=True)
        cx, cy = to_metric.transform(float(centroid[0]), float(centroid[1]))
        b = 35.0
        bbox = [cx - b, cy - b, cx + b, cy + b]

        out_path = render_candidate_composite(
            dtm_path=dtm_path,
            slrm_path=slrm_path,
            bbox_posgar=bbox,
            out_png_path=composite,
            centroid_posgar=[cx, cy],
            buffer_m=b,
            candidate_id=cid,
            include_3d_render=True,
        )
        ok.append((cid, out_path))

    print(f"✔ Láminas regeneradas a 4 paneles: {len(ok)}")
    for cid, path in ok:
        print(f"   {cid} -> {path}")
    if skipped:
        print(f"⚠ Omitidas: {len(skipped)}")
        for cid, reason in skipped:
            print(f"   {cid}: {reason}")


if __name__ == "__main__":
    main()
