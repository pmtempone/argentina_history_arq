"""Paquete de revisión ciega para especialistas externos y métricas de concordancia inter-evaluador.

Garantiza aislamiento epistémico total entre la evaluación humana y los modelos locales:
- Láminas PNG renderizadas en coordenadas métricas locales relativas (0..W m, 0..H m),
  sin coordenadas POSGAR/WGS84, sin identificadores ARQ-*, sin nombres de zona ni scores AI/VLM.
- Eliminación verificada de chunks de metadatos PNG (tEXt, iTXt, zTXt, eXIf, tIME) y EXIF.
- Clave de trazabilidad separada en ``*CONFIDENTIAL_BLIND_KEY.json`` (protegida por ``.gitignore``).
- Métricas de concordancia inter-evaluador: acuerdo porcentual + IC Wilson 95%, Cohen's κ,
  Fleiss' κ y Cohen ponderado lineal/cuadrático.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import random
import re
import struct
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import rasterio  # noqa: E402
from PIL import Image  # noqa: E402
from pyproj import Transformer  # noqa: E402
from rasterio.windows import from_bounds  # noqa: E402

from src.config import PROJECT_ROOT, settings  # noqa: E402
from src.core.benchmark_v1 import (  # noqa: E402
    _infer_zone_from_composite_path,
    _resolve_biome_for_zone,
    _resolve_dem_resolution_for_zone,
    _wilson_ci95,
)
from src.core.data_fetcher import TARGET_ZONES  # noqa: E402
from src.core.visual_inspector import _compute_multidirectional_hillshade  # noqa: E402

FORBIDDEN_PNG_CHUNKS = frozenset({b"tEXt", b"iTXt", b"zTXt", b"eXIf", b"tIME"})

BLIND_EVALUATOR_COLUMNS: Tuple[str, ...] = (
    "blind_id",
    "dem_native_resolution_m",
    "anomaly_area_m2",
    "relative_relief_m",
    "relief_sign",
    "general_biome",
    "reviewer_id",
    "decision",
    "severity_ordinal_1_to_4",
    "confidence_1_to_5",
    "diagnostic_notes",
)

GENERAL_BIOME_LABELS: Dict[str, str] = {
    "Arido_Puna": "Arido_Altoandino",
    "Arido_Andino": "Arido_Cordillerano",
    "Valles_Calchaquies": "Valles_Semiaridos",
    "Bosque_Yungas": "Selva_Pedemontana",
    "Bosque_Selva_Montana": "Selva_Montana",
    "Estepa_Patagonica": "Estepa_Fria",
    "Humedal_Llanura": "Humedal_Aluvial",
    "Estepa_Altoandina": "Estepa_Altura",
    "Bosque_Andino": "Bosque_Subantartico",
}


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _parse_png_chunk_types(png_path: Path) -> List[bytes]:
    raw = png_path.read_bytes()
    if not raw.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError(f"Archivo no es un PNG válido: {png_path}")
    pos = 8
    chunks: List[bytes] = []
    while pos + 8 <= len(raw):
        length = struct.unpack(">I", raw[pos : pos + 4])[0]
        ctype = raw[pos + 4 : pos + 8]
        chunks.append(ctype)
        pos += 12 + length
        if ctype == b"IEND":
            break
    return chunks


def strip_png_metadata_and_verify(
    src_png_path: Union[str, Path],
    dst_png_path: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """Re-codifica un PNG como RGB plano sin chunks textuales ni EXIF y verifica la limpieza."""
    src_path = Path(src_png_path).resolve()
    target_path = Path(dst_png_path).resolve() if dst_png_path is not None else src_path
    target_path.parent.mkdir(parents=True, exist_ok=True)

    with Image.open(src_path) as img:
        rgb_arr = np.asarray(img.convert("RGB"), dtype=np.uint8)

    clean_img = Image.fromarray(rgb_arr, mode="RGB")
    clean_img.save(target_path, format="PNG", optimize=True)

    with Image.open(target_path) as verified:
        exif_obj = verified.getexif()
        exif_count = len(exif_obj) if exif_obj is not None else 0
        info_keys = sorted(str(k) for k in verified.info.keys())
        width, height = verified.size

    chunk_types = _parse_png_chunk_types(target_path)
    forbidden_found = sorted({ct.decode("ascii", errors="replace") for ct in chunk_types if ct in FORBIDDEN_PNG_CHUNKS})
    if forbidden_found or exif_count > 0 or info_keys:
        raise ValueError(
            f"El PNG aún contiene metadatos prohibidos ({forbidden_found}, info={info_keys}, exif={exif_count}): {target_path}"
        )

    return {
        "path": str(target_path),
        "sha256": _sha256_file(target_path),
        "width": int(width),
        "height": int(height),
        "exif_tag_count": int(exif_count),
        "info_keys": info_keys,
        "png_chunk_types": [ct.decode("ascii", errors="replace") for ct in chunk_types],
        "forbidden_chunks_found": forbidden_found,
        "metadata_stripped_verified": True,
    }


def _clean_raster_nodata(arr: np.ndarray, nodata_val: Optional[float]) -> np.ndarray:
    out = np.asarray(arr, dtype=np.float64).copy()
    mask = ~np.isfinite(out) | (out <= -9000.0) | (out >= 1e30)
    if nodata_val is not None and np.isfinite(float(nodata_val)):
        mask |= np.isclose(out, float(nodata_val))
    out[mask] = np.nan
    return out


def _transform_bbox_to_raster_crs(
    bbox: Tuple[float, float, float, float],
    raster_crs: Any,
) -> Tuple[float, float, float, float]:
    minx, miny, maxx, maxy = (float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]))
    if minx > maxx:
        minx, maxx = maxx, minx
    if miny > maxy:
        miny, maxy = maxy, miny

    looks_like_wgs84 = (-180.0 <= minx <= 180.0 and -180.0 <= maxx <= 180.0 and -90.0 <= miny <= 90.0 and -90.0 <= maxy <= 90.0)
    if looks_like_wgs84 and raster_crs is not None and getattr(raster_crs, "is_projected", False):
        transformer = Transformer.from_crs("EPSG:4326", raster_crs, always_xy=True)
        xs = [minx, maxx, minx, maxx]
        ys = [miny, miny, maxy, maxy]
        tx, ty = transformer.transform(xs, ys)
        return (float(min(tx)), float(min(ty)), float(max(tx)), float(max(ty)))
    return (minx, miny, maxx, maxy)


def render_blind_candidate_lamina(
    dtm_path: Union[str, Path],
    slrm_path: Union[str, Path],
    bbox_posgar: Tuple[float, float, float, float],
    out_png_path: Union[str, Path],
    blind_id: str,
    buffer_m: float = 15.0,
    anomaly_area_m2: Optional[float] = None,
) -> Dict[str, Any]:
    """Renderiza una lámina ciega (Hillshade 1.5x + SLRM + perfil Δz) sin coordenadas, IDs ni scores."""
    dtm_p = Path(dtm_path).resolve()
    slrm_p = Path(slrm_path).resolve()
    dst_png = Path(out_png_path).resolve()
    dst_png.parent.mkdir(parents=True, exist_ok=True)

    with rasterio.open(dtm_p) as dtm_ds:
        rx, ry = abs(float(dtm_ds.res[0])), abs(float(dtm_ds.res[1]))
        b_minx, b_miny, b_maxx, b_maxy = _transform_bbox_to_raster_crs(bbox_posgar, dtm_ds.crs)

        cx = 0.5 * (b_minx + b_maxx)
        cy = 0.5 * (b_miny + b_maxy)
        if (b_maxx - b_minx) < 1e-3 or (b_maxy - b_miny) < 1e-3:
            half_anom = max(0.5 * math.sqrt(float(anomaly_area_m2 or 0.0)), max(rx, ry) * 0.75, 2.5)
            b_minx, b_maxx = cx - half_anom, cx + half_anom
            b_miny, b_maxy = cy - half_anom, cy + half_anom

        half_w = max(0.5 * (b_maxx - b_minx) + float(buffer_m), rx * 12.0, 12.0)
        half_h = max(0.5 * (b_maxy - b_miny) + float(buffer_m), ry * 12.0, 12.0)

        w_minx = max(float(dtm_ds.bounds.left), cx - half_w)
        w_maxx = min(float(dtm_ds.bounds.right), cx + half_w)
        w_miny = max(float(dtm_ds.bounds.bottom), cy - half_h)
        w_maxy = min(float(dtm_ds.bounds.top), cy + half_h)
        if w_maxx <= w_minx or w_maxy <= w_miny:
            raise ValueError(f"Bounding box fuera del dominio del DTM {dtm_p.name}: {(b_minx, b_miny, b_maxx, b_maxy)}")

        dtm_win = from_bounds(w_minx, w_miny, w_maxx, w_maxy, dtm_ds.transform)
        dtm_crop = _clean_raster_nodata(dtm_ds.read(1, window=dtm_win), dtm_ds.nodata)

    with rasterio.open(slrm_p) as slrm_ds:
        slrm_win = from_bounds(w_minx, w_miny, w_maxx, w_maxy, slrm_ds.transform)
        slrm_crop = _clean_raster_nodata(slrm_ds.read(1, window=slrm_win), slrm_ds.nodata)

    if dtm_crop.size == 0 or slrm_crop.size == 0:
        raise ValueError(f"Recorte vacío al generar lámina ciega {blind_id}")

    width_m = float(w_maxx - w_minx)
    height_m = float(w_maxy - w_miny)
    hillshade = _compute_multidirectional_hillshade(dtm_crop, rx, ry, z_factor=1.5)

    # Perfil transversal E-W centrado y normalizado a Δz (m) para evitar fuga de cota absoluta (e.g. Puna vs Delta)
    mid_row = slrm_crop.shape[0] // 2
    profile_raw = slrm_crop[mid_row, :]
    valid_prof = profile_raw[np.isfinite(profile_raw)]
    if valid_prof.size == 0:
        valid_dtm = dtm_crop[mid_row, :]
        valid_prof = valid_dtm[np.isfinite(valid_dtm)]
        profile_rel = dtm_crop[mid_row, :] - (float(np.nanmedian(valid_prof)) if valid_prof.size else 0.0)
    else:
        profile_rel = profile_raw - float(np.nanmedian(valid_prof))

    x_dist_m = np.linspace(0.0, width_m, num=profile_rel.shape[0])

    valid_slrm = slrm_crop[np.isfinite(slrm_crop)]
    max_abs_slrm = float(np.nanpercentile(np.abs(valid_slrm), 98.0)) if valid_slrm.size else 1.0
    vlim = max(max_abs_slrm, 0.25)

    mean_abs_sign = float(np.nanmean(valid_slrm)) if valid_slrm.size else 0.0
    rel_relief = float(np.nanmax(valid_slrm) - np.nanmin(valid_slrm)) if valid_slrm.size else 0.0
    if abs(mean_abs_sign) <= 0.05:
        relief_sign = "mixto_o_plano"
    elif mean_abs_sign > 0:
        relief_sign = "positivo"
    else:
        relief_sign = "negativo"

    # Coordenadas locales relativas de la caja central del candidato [0..width_m, 0..height_m]
    box_x0 = max(0.0, b_minx - w_minx)
    box_x1 = min(width_m, b_maxx - w_minx)
    box_y0 = max(0.0, b_miny - w_miny)
    box_y1 = min(height_m, b_maxy - w_miny)

    fig, axes = plt.subplots(1, 3, figsize=(15.0, 4.8), dpi=150)
    fig.suptitle(f"Muestra de Evaluación Ciega: {blind_id} | Escala métrica local", fontsize=12, fontweight="bold")

    extent_local = [0.0, width_m, 0.0, height_m]
    ax0, ax1, ax2 = axes

    ax0.imshow(hillshade, cmap="gray", vmin=0.0, vmax=1.0, extent=extent_local, origin="upper")
    ax0.plot([box_x0, box_x1, box_x1, box_x0, box_x0], [box_y0, box_y0, box_y1, box_y1, box_y0], "y--", lw=1.3)
    ax0.set_title("Hillshade Multidireccional 1.5x")
    ax0.set_xlabel("Este local [m]")
    ax0.set_ylabel("Norte local [m]")

    im1 = ax1.imshow(slrm_crop, cmap="RdBu_r", vmin=-vlim, vmax=vlim, extent=extent_local, origin="upper")
    ax1.plot([box_x0, box_x1, box_x1, box_x0, box_x0], [box_y0, box_y0, box_y1, box_y1, box_y0], "k--", lw=1.2)
    ax1.set_title("Modelo de Relieve Local (SLRM)")
    ax1.set_xlabel("Este local [m]")
    ax1.set_ylabel("Norte local [m]")
    cbar = fig.colorbar(im1, ax=ax1, fraction=0.046, pad=0.04)
    cbar.set_label("Δz local [m]")

    ax2.axhline(0.0, color="#64748b", linestyle=":", linewidth=1.0)
    ax2.plot(x_dist_m, np.nan_to_num(profile_rel, nan=0.0), color="#0f172a", linewidth=1.8)
    ax2.fill_between(
        x_dist_m,
        0.0,
        np.nan_to_num(profile_rel, nan=0.0),
        where=np.nan_to_num(profile_rel, nan=0.0) >= 0.0,
        alpha=0.25,
        color="#dc2626",
    )
    ax2.fill_between(
        x_dist_m,
        0.0,
        np.nan_to_num(profile_rel, nan=0.0),
        where=np.nan_to_num(profile_rel, nan=0.0) < 0.0,
        alpha=0.25,
        color="#2563eb",
    )
    ax2.set_title("Perfil Transversal E–O (Δz relativo)")
    ax2.set_xlabel("Distancia local E–O [m]")
    ax2.set_ylabel("Relieve relativo Δz [m]")
    ax2.grid(True, alpha=0.3)

    plt.tight_layout(rect=(0.0, 0.0, 1.0, 0.93))

    with tempfile.NamedTemporaryFile(suffix=".png", dir=str(dst_png.parent), delete=False) as tmp_f:
        tmp_path = Path(tmp_f.name)
    try:
        fig.savefig(tmp_path, format="png", dpi=150)
        plt.close(fig)
        strip_info = strip_png_metadata_and_verify(tmp_path, dst_png)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()

    return {
        "blind_id": blind_id,
        "image_path": str(dst_png),
        "sha256": strip_info["sha256"],
        "metadata_verification": strip_info,
        "window_width_m": round(width_m, 2),
        "window_height_m": round(height_m, 2),
        "dem_native_resolution_m": round(max(rx, ry), 4),
        "relative_relief_m": round(rel_relief, 3),
        "relief_sign": relief_sign,
        "rendered_from_geotiff": True,
    }


def _anonymize_existing_composite_png(
    src_composite_path: Union[str, Path],
    out_png_path: Union[str, Path],
    blind_id: str,
) -> Dict[str, Any]:
    """Anonimiza una lámina preexistente recortando márgenes con títulos/coordenadas y eliminando chunks."""
    src_p = Path(src_composite_path).resolve()
    dst_p = Path(out_png_path).resolve()
    dst_p.parent.mkdir(parents=True, exist_ok=True)

    with Image.open(src_p) as im:
        rgb = np.asarray(im.convert("RGB"), dtype=np.uint8).copy()
    h, w = rgb.shape[:2]
    # Enmascara banda superior de título, bordes con ejes POSGAR/WGS84 y leyenda de centroide del panel superior izquierdo
    rgb[: int(h * 0.12), :] = 255
    rgb[int(h * 0.44) : int(h * 0.55), : int(w * 0.65)] = 255
    rgb[int(h * 0.93) :, :] = 255
    rgb[:, : int(w * 0.25)] = np.where(rgb[:, : int(w * 0.25)] > 240, 255, rgb[:, : int(w * 0.25)])
    top_cut = int(h * 0.12)
    bottom_cut = int(h * 0.93)
    left_cut = int(w * 0.27)
    right_cut = int(w * 0.78)
    cropped = rgb[top_cut:bottom_cut, left_cut:right_cut]

    fig, ax = plt.subplots(figsize=(12.0, 4.8), dpi=130)
    ax.imshow(cropped)
    ax.axis("off")
    fig.suptitle(f"Muestra de Evaluación Ciega: {blind_id}", fontsize=11, fontweight="bold")
    plt.tight_layout(rect=(0.0, 0.0, 1.0, 0.94))

    with tempfile.NamedTemporaryFile(suffix=".png", dir=str(dst_p.parent), delete=False) as tmp_f:
        tmp_path = Path(tmp_f.name)
    try:
        fig.savefig(tmp_path, format="png", dpi=130)
        plt.close(fig)
        strip_info = strip_png_metadata_and_verify(tmp_path, dst_p)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()

    return {
        "blind_id": blind_id,
        "image_path": str(dst_p),
        "sha256": strip_info["sha256"],
        "metadata_verification": strip_info,
        "rendered_from_geotiff": False,
    }


def _resolve_zone_rasters(
    zone_key: str,
    raw_dir: Path,
    processed_dir: Path,
) -> Tuple[Optional[Path], Optional[Path]]:
    """Resuelve rutas locales a (dtm_posgar_o_raw, master_slrm) para una zona dada."""
    zone_norm = zone_key.strip().lower()
    slrm_candidates = [
        processed_dir / f"{zone_norm}_master_slrm.tif",
        processed_dir / f"{zone_norm}_slrm.tif",
    ]
    slrm_path = next((p for p in slrm_candidates if p.exists()), None)

    dtm_candidates: List[Path] = []
    if zone_norm == "highres_san_juan_uav":
        dtm_candidates.extend(
            [
                raw_dir / "highres" / "zenodo_18023344_posgar_5344.tif",
                raw_dir / "highres" / "zenodo_18023344_raw.tif",
            ]
        )
    elif zone_norm == "highres_zenodo_3383227":
        dtm_candidates.extend(
            [
                raw_dir / "highres" / "zenodo_3383227_posgar_5344.tif",
                raw_dir / "highres" / "zenodo_3383227_raw.tif",
            ]
        )
    else:
        dtm_candidates.extend(sorted(raw_dir.glob(f"{zone_norm}_posgar_*.tif")))
        dtm_candidates.extend(sorted(raw_dir.glob(f"{zone_norm}_*wgs84.tif")))
    dtm_path = next((p for p in dtm_candidates if p.exists()), None)
    return dtm_path, slrm_path


def _geom_bbox(geom: Dict[str, Any]) -> Optional[Tuple[float, float, float, float]]:
    gtype = geom.get("type")
    coords = geom.get("coordinates")
    if not coords:
        return None
    pts: List[Tuple[float, float]] = []
    if gtype == "Point":
        pts.append((float(coords[0]), float(coords[1])))
    elif gtype == "Polygon":
        for ring in coords:
            for pt in ring:
                pts.append((float(pt[0]), float(pt[1])))
    elif gtype == "MultiPolygon":
        for poly in coords:
            for ring in poly:
                for pt in ring:
                    pts.append((float(pt[0]), float(pt[1])))
    if not pts:
        return None
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return (min(xs), min(ys), max(xs), max(ys))


def _collect_local_pool(
    reports_dir: Path,
    processed_dir: Path,
    raw_dir: Path,
) -> List[Dict[str, Any]]:
    """Recolecta candidatos reales locales (excluyendo sintéticos) uniendo DESCARTES_VLM y MAPA_PROSPECCION."""
    feature_index: Dict[str, Dict[str, Any]] = {}
    for gjson_path in sorted(reports_dir.glob("MAPA_PROSPECCION_*.geojson")):
        zone_hint = gjson_path.stem.replace("MAPA_PROSPECCION_", "").lower()
        try:
            payload = json.loads(gjson_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        for feat in payload.get("features", []):
            props = feat.get("properties") or {}
            cid = str(props.get("id") or "").strip()
            if not cid or cid.startswith("INV-") or cid.startswith("SYN"):
                continue
            bbox = _geom_bbox(feat.get("geometry") or {})
            feature_index[cid] = {
                "zone_hint": zone_hint,
                "bbox": bbox,
                "props": props,
            }

    inv_path = reports_dir / "INVENTARIO_GEOMORFOLOGICO.geojson"
    if inv_path.exists():
        try:
            inv_payload = json.loads(inv_path.read_text(encoding="utf-8"))
            for feat in inv_payload.get("features", []):
                props = feat.get("properties") or {}
                cid = str(props.get("id") or "").strip()
                if not cid or cid in feature_index or cid.startswith("INV-") or cid.startswith("SYN"):
                    continue
                bbox = _geom_bbox(feat.get("geometry") or {})
                if bbox is not None:
                    feature_index[cid] = {
                        "zone_hint": "",
                        "bbox": bbox,
                        "props": props,
                    }
        except Exception:
            pass

    pool: List[Dict[str, Any]] = []
    seen_ids = set()

    descartes_path = reports_dir / "DESCARTES_VLM.json"
    if descartes_path.exists():
        raw_desc = json.loads(descartes_path.read_text(encoding="utf-8"))
        for cid, rec in sorted((raw_desc.get("discarded") or {}).items()):
            comp_rel = str(rec.get("composite_image_path") or "")
            if "synthetic" in comp_rel.lower():
                continue
            zone_key = _infer_zone_from_composite_path(comp_rel, cid) or ""
            fmeta = feature_index.get(cid, {})
            if not zone_key:
                zone_key = str(fmeta.get("zone_hint") or "")
            if not zone_key:
                continue

            props = fmeta.get("props") or {}
            vlm_v = rec.get("vlm_verdict") or {}
            comp_path = Path(comp_rel)
            if not comp_path.is_absolute():
                comp_path = PROJECT_ROOT / comp_path
            dtm_path, slrm_path = _resolve_zone_rasters(zone_key, raw_dir, processed_dir)
            bbox = fmeta.get("bbox")
            if dtm_path is None and not comp_path.exists():
                continue

            biome_raw = _resolve_biome_for_zone(zone_key, TARGET_ZONES)
            dem_res = float(props.get("dem_native_resolution_m") or _resolve_dem_resolution_for_zone(zone_key))
            seen_ids.add(cid)
            pool.append(
                {
                    "candidate_id": cid,
                    "zone_key": zone_key,
                    "general_biome": GENERAL_BIOME_LABELS.get(biome_raw, biome_raw),
                    "dem_native_resolution_m": dem_res,
                    "area_m2": float(rec.get("area_m2") or props.get("area_m2") or 0.0),
                    "relative_relief_m": round(abs(float(rec.get("mean_elevation_m") or props.get("mean_elevation_m") or 0.0)), 3),
                    "relief_sign": "negativo" if float(rec.get("mean_elevation_m") or 0.0) < -0.05 else "positivo",
                    "ai_vlm_verdict": str(vlm_v.get("verdict") or "UNKNOWN"),
                    "source_origin": "AI_REJECTED_CANDIDATE",
                    "bbox": bbox,
                    "dtm_path": str(dtm_path) if dtm_path else None,
                    "slrm_path": str(slrm_path) if slrm_path else None,
                    "composite_path": str(comp_path) if comp_path.exists() else None,
                }
            )

    # Incorpora también candidatos pendientes o inéditos presentes en MAPA_PROSPECCION_* con rasters/composites locales
    for cid, fmeta in sorted(feature_index.items()):
        if cid in seen_ids:
            continue
        zone_key = str(fmeta.get("zone_hint") or "")
        if not zone_key or "synthetic" in zone_key:
            continue
        props = fmeta.get("props") or {}
        comp_rel = str(props.get("composite_image_path") or "")
        comp_path = Path(comp_rel)
        if comp_rel and not comp_path.is_absolute():
            comp_path = PROJECT_ROOT / comp_path
        dtm_path, slrm_path = _resolve_zone_rasters(zone_key, raw_dir, processed_dir)
        if dtm_path is None and not (comp_rel and comp_path.exists()):
            continue

        biome_raw = _resolve_biome_for_zone(zone_key, TARGET_ZONES)
        vlm_v = props.get("vlm_verdict") or {}
        mean_elev = float(props.get("mean_elevation_m") or 0.0)
        pool.append(
            {
                "candidate_id": cid,
                "zone_key": zone_key,
                "general_biome": GENERAL_BIOME_LABELS.get(biome_raw, biome_raw),
                "dem_native_resolution_m": float(props.get("dem_native_resolution_m") or _resolve_dem_resolution_for_zone(zone_key)),
                "area_m2": float(props.get("area_m2") or 0.0),
                "relative_relief_m": round(abs(mean_elev), 3),
                "relief_sign": "negativo" if mean_elev < -0.05 else "positivo",
                "ai_vlm_verdict": str(vlm_v.get("verdict") or "PENDIENTE_REVISION"),
                "source_origin": "ALGORITMIC_DETECTION",
                "bbox": fmeta.get("bbox"),
                "dtm_path": str(dtm_path) if dtm_path else None,
                "slrm_path": str(slrm_path) if slrm_path else None,
                "composite_path": str(comp_path) if comp_rel and comp_path.exists() else None,
            }
        )

    return pool


def _stratified_blind_sample(pool: List[Dict[str, Any]], max_items: int, seed: int) -> List[Dict[str, Any]]:
    geotiff_ready = [
        item
        for item in pool
        if item.get("dtm_path")
        and item.get("slrm_path")
        and item.get("bbox") is not None
        and Path(str(item["dtm_path"])).exists()
        and Path(str(item["slrm_path"])).exists()
    ]
    effective_pool = geotiff_ready if geotiff_ready else list(pool)

    if len(effective_pool) <= max_items:
        sampled = list(effective_pool)
        random.Random(seed).shuffle(sampled)
        return sampled

    rng = random.Random(seed)
    by_verdict: Dict[str, List[Dict[str, Any]]] = {}
    for item in effective_pool:
        key = str(item.get("ai_vlm_verdict") or "UNKNOWN")
        by_verdict.setdefault(key, []).append(item)

    for grp in by_verdict.values():
        rng.shuffle(grp)

    selected: List[Dict[str, Any]] = []
    verdict_keys = sorted(by_verdict.keys())
    idx = 0
    while len(selected) < max_items and any(by_verdict.values()):
        k = verdict_keys[idx % len(verdict_keys)]
        if by_verdict[k]:
            # Priorizar diversidad de zonas y resoluciones cuando hay opciones
            selected.append(by_verdict[k].pop(0))
        idx += 1

    rng.shuffle(selected)
    return selected


def _write_evaluator_instructions(dst_path: Path) -> None:
    content = """# Protocolo de Evaluación Ciega — ArchaeoLiDAR-AR

Gracias por participar como especialista independiente. Este paquete contiene láminas geomorfológicas
totalmente anonimizadas (`images/BLIND-XXXX.png`) y una planilla neutral (`evaluator_sheet_template.csv`).

## Garantía de cegamiento
- Las imágenes muestran exclusivamente ejes métricos locales (`0..W m`, `0..H m`) y relieve relativo `Δz [m]`.
- No se incluyen coordenadas geográficas, códigos de sitio, regiones administrativas ni dictámenes o puntajes de modelos de IA.
- Todos los metadatos PNG/EXIF fueron eliminados y verificados criptográficamente (SHA-256).

## Taxonomía de decisión (`decision`)
- `ARCHAEOLOGICAL_PLAUSIBLE`: Geometría coherente con estructura antrópica prehistórica/histórica (p. ej. recinto ortogonal, canchón, terraza, casa-pozo, estructura defensiva).
- `NATURAL_GEOFORM`: Geoforma natural o artefacto de interpolación/ruido del DEM sin indicios constructivos antrópicos.
- `MODERN_INFRASTRUCTURE`: Alambrado, huella vehicular, pirca moderna, obra hidráulica actual o infraestructura contemporánea.
- `INCONCLUSIVE`: La resolución o contraste topográfico del recorte no permite una discriminación confiable.

## Escala ordinal de plausibilidad arqueológica (`severity_ordinal_1_to_4`)
- `1`: Descartado / claramente natural o moderno.
- `2`: Improbable / señal muy débil o ambigua.
- `3`: Plausible / merece segunda inspección y contexto documental.
- `4`: Altamente plausible / prioridad de verificación en campo.
"""
    dst_path.write_text(content, encoding="utf-8")


def export_blind_review_pack(
    out_dir: Optional[Union[str, Path]] = None,
    reports_dir: Optional[Union[str, Path]] = None,
    processed_dir: Optional[Union[str, Path]] = None,
    raw_dir: Optional[Union[str, Path]] = None,
    items: Optional[Sequence[Dict[str, Any]]] = None,
    max_items: int = 12,
    seed: int = 42,
) -> Dict[str, Any]:
    """Genera un paquete de revisión ciega anonimizado con láminas PNG sin metadatos, CSV neutral y clave secreta."""
    target_dir = Path(out_dir).resolve() if out_dir is not None else (settings.processed_dir / "blind_review_pack").resolve()
    rep_dir = Path(reports_dir).resolve() if reports_dir is not None else settings.reports_dir.resolve()
    proc_dir = Path(processed_dir).resolve() if processed_dir is not None else settings.processed_dir.resolve()
    r_dir = Path(raw_dir).resolve() if raw_dir is not None else settings.data_dir.resolve()

    images_dir = target_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    pool = list(items) if items is not None else _collect_local_pool(rep_dir, proc_dir, r_dir)
    if not pool:
        raise ValueError("No se encontraron candidatos elegibles para construir el paquete de revisión ciega.")

    selected = _stratified_blind_sample(pool, max_items=max_items, seed=seed)

    manifest_items: List[Dict[str, Any]] = []
    key_entries: List[Dict[str, Any]] = []
    csv_rows: List[Dict[str, Any]] = []

    for i, item in enumerate(selected, start=1):
        blind_id = f"BLIND-{i:04d}"
        out_img = images_dir / f"{blind_id}.png"

        dtm_path = item.get("dtm_path")
        slrm_path = item.get("slrm_path")
        bbox = item.get("bbox")
        comp_path = item.get("composite_path")

        if dtm_path and slrm_path and bbox is not None and Path(dtm_path).exists() and Path(slrm_path).exists():
            render_res = render_blind_candidate_lamina(
                dtm_path=dtm_path,
                slrm_path=slrm_path,
                bbox_posgar=tuple(bbox),
                out_png_path=out_img,
                blind_id=blind_id,
                anomaly_area_m2=float(item.get("area_m2") or 0.0) or None,
            )
            rel_relief = render_res["relative_relief_m"]
            relief_sign = render_res["relief_sign"]
            dem_res = render_res["dem_native_resolution_m"]
            sha256_img = render_res["sha256"]
            rendered_from_geotiff = True
        elif comp_path and Path(comp_path).exists():
            anon_res = _anonymize_existing_composite_png(comp_path, out_img, blind_id)
            rel_relief = float(item.get("relative_relief_m") or 0.0)
            relief_sign = str(item.get("relief_sign") or "mixto")
            dem_res = float(item.get("dem_native_resolution_m") or 30.0)
            sha256_img = anon_res["sha256"]
            rendered_from_geotiff = False
        else:
            raise FileNotFoundError(f"Sin GeoTIFF ni composite válido para {item.get('candidate_id', blind_id)}")

        biome_label = str(item.get("general_biome") or GENERAL_BIOME_LABELS.get(str(item.get("biome") or ""), "No_Especificado"))
        area_m2 = round(float(item.get("area_m2") or 0.0), 2)

        csv_rows.append(
            {
                "blind_id": blind_id,
                "dem_native_resolution_m": round(float(dem_res), 3),
                "anomaly_area_m2": area_m2,
                "relative_relief_m": round(float(rel_relief), 3),
                "relief_sign": relief_sign,
                "general_biome": biome_label,
                "reviewer_id": "",
                "decision": "",
                "severity_ordinal_1_to_4": "",
                "confidence_1_to_5": "",
                "diagnostic_notes": "",
            }
        )

        manifest_items.append(
            {
                "blind_id": blind_id,
                "image_relpath": f"images/{blind_id}.png",
                "sha256": sha256_img,
                "metadata_stripped_verified": True,
                "rendered_from_geotiff": rendered_from_geotiff,
                "dem_native_resolution_m": round(float(dem_res), 3),
                "general_biome": biome_label,
            }
        )

        key_entries.append(
            {
                "blind_id": blind_id,
                "candidate_id": item.get("candidate_id"),
                "zone_key": item.get("zone_key"),
                "source_origin": item.get("source_origin", "UNKNOWN"),
                "ai_vlm_verdict": item.get("ai_vlm_verdict"),
                "dem_native_resolution_m": round(float(dem_res), 3),
                "image_relpath": f"images/{blind_id}.png",
                "sha256_image": sha256_img,
                "metadata_stripped_verified": True,
            }
        )

    csv_path = target_dir / "evaluator_sheet_template.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(BLIND_EVALUATOR_COLUMNS))
        writer.writeheader()
        writer.writerows(csv_rows)

    instructions_path = target_dir / "EVALUATOR_INSTRUCTIONS.md"
    _write_evaluator_instructions(instructions_path)

    manifest_path = target_dir / "BLIND_REVIEW_PACK_MANIFEST.json"
    manifest_payload = {
        "schema_version": "blind-review-pack-v1.0",
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "seed": int(seed),
        "n_items": len(manifest_items),
        "blinded_garantees": {
            "coordinates_excluded": True,
            "candidate_ids_excluded": True,
            "zone_names_excluded": True,
            "ai_scores_and_verdicts_excluded": True,
            "png_exif_and_text_chunks_stripped": True,
        },
        "items": manifest_items,
    }
    manifest_path.write_text(json.dumps(manifest_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    key_path = target_dir / "CONFIDENTIAL_BLIND_KEY.json"
    key_payload = {
        "warning": "CONFIDENCIAL (Ley 25.743 / Integridad de evaluación ciega). NO compartir con evaluadores ni versionar.",
        "generated_at_utc": manifest_payload["generated_at_utc"],
        "seed": int(seed),
        "n_items": len(key_entries),
        "manifest_sha256": _sha256_file(manifest_path),
        "csv_template_sha256": _sha256_file(csv_path),
        "mapping": key_entries,
    }
    key_path.write_text(json.dumps(key_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    return {
        "out_dir": str(target_dir),
        "n_items": len(manifest_items),
        "manifest_path": str(manifest_path),
        "evaluator_csv_path": str(csv_path),
        "instructions_path": str(instructions_path),
        "confidential_key_path": str(key_path),
        "all_metadata_stripped_verified": all(m["metadata_stripped_verified"] for m in manifest_items),
    }


def _landis_koch_band(kappa: Optional[float]) -> str:
    if kappa is None:
        return "Indeterminado (varianza marginal nula)"
    if kappa < 0.0:
        return "Pobre (< 0.00)"
    if kappa <= 0.20:
        return "Leve (0.00 - 0.20)"
    if kappa <= 0.40:
        return "Aceptable (0.21 - 0.40)"
    if kappa <= 0.60:
        return "Moderado (0.41 - 0.60)"
    if kappa <= 0.80:
        return "Sustancial (0.61 - 0.80)"
    return "Casi perfecto (0.81 - 1.00)"


def _pairwise_cohen_and_weighted(
    r0: Sequence[Any],
    r1: Sequence[Any],
    categories: Sequence[Any],
) -> Dict[str, Optional[float]]:
    n = len(r0)
    k_cat = len(categories)
    idx_map = {cat: idx for idx, cat in enumerate(categories)}
    mat = np.zeros((k_cat, k_cat), dtype=np.float64)
    for a, b in zip(r0, r1):
        if a not in idx_map or b not in idx_map:
            raise ValueError(f"Categoría fuera del dominio declarado {categories}: {(a, b)}")
        mat[idx_map[a], idx_map[b]] += 1.0

    obs = mat / float(n)
    row_m = obs.sum(axis=1)
    col_m = obs.sum(axis=0)
    expected = np.outer(row_m, col_m)

    po = float(np.trace(obs))
    pe = float(np.trace(expected))
    cohens = None if abs(1.0 - pe) <= 1e-12 else float((po - pe) / (1.0 - pe))

    if k_cat < 2:
        return {"cohens_kappa": cohens, "weighted_linear": None, "weighted_quadratic": None}

    ii, jj = np.indices((k_cat, k_cat), dtype=np.float64)
    denom_k = float(k_cat - 1)
    w_lin = np.abs(ii - jj) / denom_k
    w_quad = ((ii - jj) ** 2) / (denom_k**2)

    exp_lin = float(np.sum(w_lin * expected))
    exp_quad = float(np.sum(w_quad * expected))
    w_lin_k = None if exp_lin <= 1e-12 else float(1.0 - np.sum(w_lin * obs) / exp_lin)
    w_quad_k = None if exp_quad <= 1e-12 else float(1.0 - np.sum(w_quad * obs) / exp_quad)
    return {
        "cohens_kappa": round(cohens, 6) if cohens is not None else None,
        "weighted_linear": round(w_lin_k, 6) if w_lin_k is not None else None,
        "weighted_quadratic": round(w_quad_k, 6) if w_quad_k is not None else None,
    }


def compute_inter_rater_agreement(
    ratings_matrix: Sequence[Sequence[Any]],
    categories: Optional[Sequence[Any]] = None,
) -> Dict[str, Any]:
    """Calcula concordancia inter-evaluador sobre una matriz (n_items x n_raters).

    Retorna:
    - percent_agreement y su IC Wilson 95% (pares concordantes / total de pares entre evaluadores).
    - exact_unanimous_rate y su IC Wilson 95%.
    - fleiss_kappa (para m >= 2 evaluadores).
    - cohens_kappa (exacto para m == 2; promedio de pares para m > 2).
    - weighted_kappa_linear y weighted_kappa_quadratic usando el orden de ``categories`` (o sort natural).
    """
    rows = [list(r) for r in ratings_matrix]
    n_items = len(rows)
    if n_items == 0:
        raise ValueError("ratings_matrix no puede estar vacía.")
    n_raters = len(rows[0])
    if n_raters < 2:
        raise ValueError("Se requieren al menos 2 evaluadores por ítem para calcular concordancia.")
    if any(len(r) != n_raters for r in rows):
        raise ValueError("Todas las filas de ratings_matrix deben tener la misma cantidad de evaluadores.")

    if categories is None:
        observed_vals = {val for row in rows for val in row}
        try:
            cats = sorted(observed_vals)
        except TypeError:
            cats = sorted(observed_vals, key=str)
    else:
        cats = list(categories)

    cat_idx = {c: idx for idx, c in enumerate(cats)}
    k_cats = len(cats)

    # Matriz de conteos n_ij (n_items x k_cats) para Fleiss y acuerdos por pares
    counts = np.zeros((n_items, k_cats), dtype=np.int64)
    for i, row in enumerate(rows):
        for val in row:
            if val not in cat_idx:
                raise ValueError(f"Valor '{val}' fuera de categories={cats}")
            counts[i, cat_idx[val]] += 1

    pairs_per_item = n_raters * (n_raters - 1) // 2
    agree_pairs_per_item = np.sum(counts * (counts - 1) // 2, axis=1)
    total_agree_pairs = int(np.sum(agree_pairs_per_item))
    total_pairs = int(n_items * pairs_per_item)

    p_bar = float(total_agree_pairs / total_pairs)
    percent_ci = _wilson_ci95(total_agree_pairs, total_pairs)

    unanimous_items = int(np.sum(np.max(counts, axis=1) == n_raters))
    unanimous_ci = _wilson_ci95(unanimous_items, n_items)

    # Fleiss' kappa
    p_j = np.sum(counts, axis=0) / float(n_items * n_raters)
    p_e_fleiss = float(np.sum(p_j**2))
    fleiss_k = None if abs(1.0 - p_e_fleiss) <= 1e-12 else round(float((p_bar - p_e_fleiss) / (1.0 - p_e_fleiss)), 6)

    # Cohen y Weighted kappa (para 2 raters directo; para >2 raters promedio de los C(m,2) pares)
    cohen_list: List[float] = []
    wlin_list: List[float] = []
    wquad_list: List[float] = []
    for r_a in range(n_raters):
        for r_b in range(r_a + 1, n_raters):
            col_a = [row[r_a] for row in rows]
            col_b = [row[r_b] for row in rows]
            pw = _pairwise_cohen_and_weighted(col_a, col_b, cats)
            if pw["cohens_kappa"] is not None:
                cohen_list.append(pw["cohens_kappa"])
            if pw["weighted_linear"] is not None:
                wlin_list.append(pw["weighted_linear"])
            if pw["weighted_quadratic"] is not None:
                wquad_list.append(pw["weighted_quadratic"])

    cohens_k = round(float(np.mean(cohen_list)), 6) if cohen_list else None
    wlin_k = round(float(np.mean(wlin_list)), 6) if wlin_list else None
    wquad_k = round(float(np.mean(wquad_list)), 6) if wquad_list else None

    primary_k = fleiss_k if n_raters > 2 else (cohens_k if cohens_k is not None else fleiss_k)
    return {
        "n_items": int(n_items),
        "n_raters": int(n_raters),
        "categories": cats,
        "percent_agreement": round(p_bar, 6),
        "percent_agreement_wilson_ci95": percent_ci,
        "agree_pairs": total_agree_pairs,
        "total_pairs": total_pairs,
        "exact_unanimous_rate": round(float(unanimous_items / n_items), 6),
        "exact_unanimous_wilson_ci95": unanimous_ci,
        "cohens_kappa": cohens_k,
        "fleiss_kappa": fleiss_k,
        "weighted_kappa_linear": wlin_k,
        "weighted_kappa_quadratic": wquad_k,
        "degenerate_single_class": bool(abs(1.0 - p_e_fleiss) <= 1e-12),
        "interpretation": _landis_koch_band(primary_k),
        "category_marginals": {str(c): round(float(p_j[idx]), 6) for idx, c in enumerate(cats)},
    }


def evaluate_blind_evaluator_sheets(
    csv_paths: Sequence[Union[str, Path]],
    decision_categories: Optional[Sequence[str]] = None,
    ordinal_levels: Sequence[int] = (1, 2, 3, 4),
) -> Dict[str, Any]:
    """Consolida 2 o más planillas CSV devueltas por evaluadores y calcula concordancia nominal y ordinal."""
    if len(csv_paths) < 2:
        raise ValueError("Se requieren al menos 2 planillas CSV de evaluadores para calcular concordancia.")

    per_rater: List[Dict[str, Dict[str, Any]]] = []
    for idx, p in enumerate(csv_paths, start=1):
        rows_by_id: Dict[str, Dict[str, Any]] = {}
        with Path(p).open("r", encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                bid = str(row.get("blind_id") or "").strip()
                dec = str(row.get("decision") or "").strip()
                if not bid or not dec:
                    continue
                sev_raw = str(row.get("severity_ordinal_1_to_4") or "").strip()
                rows_by_id[bid] = {
                    "decision": dec,
                    "severity": int(sev_raw) if re.fullmatch(r"\d+", sev_raw) else None,
                    "reviewer_id": str(row.get("reviewer_id") or f"rater_{idx}").strip(),
                }
        per_rater.append(rows_by_id)

    common_ids = sorted(set.intersection(*(set(d.keys()) for d in per_rater)))
    if not common_ids:
        raise ValueError("No hay blind_id comunes con decisiones completadas entre las planillas provistas.")

    dec_matrix = [[d[bid]["decision"] for d in per_rater] for bid in common_ids]
    nominal_report = compute_inter_rater_agreement(dec_matrix, categories=decision_categories)

    ord_ids = [bid for bid in common_ids if all(d[bid]["severity"] is not None for d in per_rater)]
    ordinal_report: Optional[Dict[str, Any]] = None
    if ord_ids:
        ord_matrix = [[int(d[bid]["severity"]) for d in per_rater] for bid in ord_ids]
        ordinal_report = compute_inter_rater_agreement(ord_matrix, categories=list(ordinal_levels))

    return {
        "n_raters": len(csv_paths),
        "common_blind_ids": common_ids,
        "nominal_decision_agreement": nominal_report,
        "ordinal_severity_agreement": ordinal_report,
    }
