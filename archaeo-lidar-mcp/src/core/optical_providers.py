"""Proveedor óptico y multiespectral por candidato (Sentinel-2 L2A STAC + Chips RGB XYZ/GEE).

Reglas de diseño y presupuesto de red:
1. NUNCA se ejecuta a nivel de zona completa ni sobre celdas descartadas.
2. Opera exclusivamente en Fase 4 sobre candidatos `CANDIDATO_INEDITO` (parche de ~300x300 m:
   `bbox_posgar ± settings.optical_buffer_m`).
3. En Sentinel-2 L2A (Element 84 Earth Search STAC, 10 m/px), lee únicamente la ventana de
   ~30x30 px por banda (< 15 KB) usando HTTP Range Requests.
4. En chips RGB de alta resolución (XYZ / GEE), aplica un tope duro de `512x512 px` (< 250 KB).
"""

import io
import logging
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import cv2
import httpx
import numpy as np
import rasterio
from pyproj import CRS, Transformer
from rasterio.windows import from_bounds
from shapely.geometry import Polygon, shape

from src.config import settings

logger = logging.getLogger(__name__)


def _posgar_patch_to_wgs84_bbox(
    bbox_posgar: Sequence[float],
    crs_epsg: int,
    buffer_m: float,
) -> Tuple[Tuple[float, float, float, float], Tuple[float, float, float, float]]:
    """Retorna `(patch_bbox_posgar, patch_bbox_wgs84)` expandido por `buffer_m`."""
    minx, miny, maxx, maxy = [float(v) for v in bbox_posgar]
    p_minx = minx - float(buffer_m)
    p_miny = miny - float(buffer_m)
    p_maxx = maxx + float(buffer_m)
    p_maxy = maxy + float(buffer_m)

    to_wgs = Transformer.from_crs(CRS.from_epsg(crs_epsg), CRS.from_epsg(4326), always_xy=True)
    lon1, lat1 = to_wgs.transform(p_minx, p_miny)
    lon2, lat2 = to_wgs.transform(p_maxx, p_maxy)
    return (
        (p_minx, p_miny, p_maxx, p_maxy),
        (min(lon1, lon2), min(lat1, lat2), max(lon1, lon2), max(lat1, lat2)),
    )


def cap_rgb_chip_size(rgb: np.ndarray, max_side_px: Optional[int] = None) -> np.ndarray:
    """Garantiza que el chip RGB no supere `max_optical_chip_px` (512x512 px por defecto)."""
    cap = int(max_side_px or settings.max_optical_chip_px)
    h, w = rgb.shape[:2]
    if max(h, w) <= cap:
        return rgb
    scale = cap / float(max(h, w))
    new_w = max(1, int(round(w * scale)))
    new_h = max(1, int(round(h * scale)))
    return cv2.resize(rgb, (new_w, new_h), interpolation=cv2.INTER_AREA)


def compute_spectral_indices_and_stats(
    red: np.ndarray,
    green: np.ndarray,
    nir: np.ndarray,
    inside_mask: Optional[np.ndarray] = None,
) -> Dict[str, Any]:
    """Calcula NDVI, NDWI y contraste diferencial (`ndvi_anomaly_delta`) dentro vs. anillo exterior."""
    r = red.astype(np.float64)
    g = green.astype(np.float64)
    n = nir.astype(np.float64)

    ndvi = (n - r) / (n + r + 1e-6)
    ndwi = (g - n) / (g + n + 1e-6)

    valid = np.isfinite(ndvi) & np.isfinite(ndwi)
    if not np.any(valid):
        return {
            "ndvi": ndvi,
            "ndwi": ndwi,
            "ndvi_mean": None,
            "ndvi_std": None,
            "ndwi_mean": None,
            "ndvi_anomaly_delta": None,
        }

    ndvi_mean = float(np.nanmean(ndvi[valid]))
    ndvi_std = float(np.nanstd(ndvi[valid]))
    ndwi_mean = float(np.nanmean(ndwi[valid]))

    if inside_mask is not None and np.any(inside_mask & valid) and np.any((~inside_mask) & valid):
        inside_val = float(np.nanmean(ndvi[inside_mask & valid]))
        ring_val = float(np.nanmean(ndvi[(~inside_mask) & valid]))
        ndvi_delta = round(inside_val - ring_val, 4)
    else:
        # Si no hay máscara poligonal explícita, usar núcleo central vs. borde del parche
        h, w = ndvi.shape
        r0, r1 = max(0, h // 3), min(h, (2 * h) // 3)
        c0, c1 = max(0, w // 3), min(w, (2 * w) // 3)
        core_mask = np.zeros((h, w), dtype=bool)
        core_mask[r0:r1, c0:c1] = True
        if np.any(core_mask & valid) and np.any((~core_mask) & valid):
            ndvi_delta = round(float(np.nanmean(ndvi[core_mask & valid]) - np.nanmean(ndvi[(~core_mask) & valid])), 4)
        else:
            ndvi_delta = 0.0

    return {
        "ndvi": ndvi.astype(np.float32),
        "ndwi": ndwi.astype(np.float32),
        "ndvi_mean": round(ndvi_mean, 4),
        "ndvi_std": round(ndvi_std, 4),
        "ndwi_mean": round(ndwi_mean, 4),
        "ndvi_anomaly_delta": float(ndvi_delta),
    }


def _build_inside_mask_from_geometry(
    geometry_wgs84: Optional[Dict[str, Any]],
    patch_bbox_posgar: Tuple[float, float, float, float],
    crs_epsg: int,
    shape_hw: Tuple[int, int],
) -> Optional[np.ndarray]:
    """Rasteriza la geometría del candidato en la grilla `(H, W)` del parche métrico."""
    if not geometry_wgs84:
        return None
    try:
        geom = shape(geometry_wgs84)
        to_metric = Transformer.from_crs(CRS.from_epsg(4326), CRS.from_epsg(crs_epsg), always_xy=True)
        h, w = shape_hw
        minx, miny, maxx, maxy = patch_bbox_posgar
        dx = (maxx - minx) / max(1, w)
        dy = (maxy - miny) / max(1, h)
        ring_pts = list(geom.exterior.coords) if isinstance(geom, Polygon) else list(geom.geoms[0].exterior.coords)
        px_pts = []
        for lon, lat in ring_pts:
            mx, my = to_metric.transform(float(lon), float(lat))
            col = int(round((mx - minx) / dx))
            row = int(round((maxy - my) / dy))
            px_pts.append([col, row])
        mask_u8 = np.zeros((h, w), dtype=np.uint8)
        cv2.fillPoly(mask_u8, [np.array(px_pts, dtype=np.int32)], 1)
        return mask_u8.astype(bool)
    except Exception:
        return None


def _read_cog_patch_band(
    href: str,
    patch_bbox_wgs84: Tuple[float, float, float, float],
    target_shape: Optional[Tuple[int, int]] = None,
) -> np.ndarray:
    """Lee únicamente el recorte `patch_bbox_wgs84` de una banda COG remota vía HTTP Range Request."""
    min_lon, min_lat, max_lon, max_lat = patch_bbox_wgs84
    with rasterio.open(href) as src:
        to_src = Transformer.from_crs(CRS.from_epsg(4326), src.crs, always_xy=True)
        sx1, sy1 = to_src.transform(min_lon, min_lat)
        sx2, sy2 = to_src.transform(max_lon, max_lat)
        win = from_bounds(min(sx1, sx2), min(sy1, sy2), max(sx1, sx2), max(sy1, sy2), transform=src.transform)
        win = win.round_offsets().round_lengths()
        arr = src.read(1, window=win, boundless=True, fill_value=0).astype(np.float32)

    if target_shape is not None and arr.shape != target_shape:
        arr = cv2.resize(arr, (target_shape[1], target_shape[0]), interpolation=cv2.INTER_LINEAR)
    return arr


def _fetch_sentinel2_stac_patch(
    centroid_wgs84: Sequence[float],
    patch_bbox_wgs84: Tuple[float, float, float, float],
    patch_bbox_posgar: Tuple[float, float, float, float],
    crs_epsg: int,
    geometry_wgs84: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Consulta Sentinel-2 L2A vía Element 84 Earth Search STAC y descarga solo la ventana ~30x30 px."""
    from pystac_client import Client

    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=730)
    dt_range = f"{start_dt.strftime('%Y-%m-%d')}/{end_dt.strftime('%Y-%m-%d')}"

    client = Client.open(settings.earth_search_stac_url)
    search = client.search(
        collections=["sentinel-2-l2a"],
        intersects={"type": "Point", "coordinates": [float(centroid_wgs84[0]), float(centroid_wgs84[1])]},
        datetime=dt_range,
        query={"eo:cloud_cover": {"lt": 15}},
        max_items=10,
    )
    items = list(search.items())
    if not items:
        return None

    items.sort(key=lambda it: float(it.properties.get("eo:cloud_cover", 100.0)))
    best = items[0]

    red_href = best.assets["red"].href
    green_href = best.assets["green"].href
    blue_href = best.assets["blue"].href
    nir_href = best.assets["nir"].href

    red = _read_cog_patch_band(red_href, patch_bbox_wgs84)
    target_hw = red.shape
    green = _read_cog_patch_band(green_href, patch_bbox_wgs84, target_shape=target_hw)
    blue = _read_cog_patch_band(blue_href, patch_bbox_wgs84, target_shape=target_hw)
    nir = _read_cog_patch_band(nir_href, patch_bbox_wgs84, target_shape=target_hw)

    inside_mask = _build_inside_mask_from_geometry(geometry_wgs84, patch_bbox_posgar, crs_epsg, target_hw)
    spec = compute_spectral_indices_and_stats(red=red, green=green, nir=nir, inside_mask=inside_mask)

    # Normalizar RGB Sentinel-2 (reflectancia 0..3500 -> uint8)
    rgb_stack = np.stack([red, green, blue], axis=-1)
    rgb_u8 = np.clip((rgb_stack / 3500.0) * 255.0, 0, 255).astype(np.uint8)
    rgb_u8 = cap_rgb_chip_size(rgb_u8)

    return {
        "optical_provider_used": "sentinel2_stac",
        "scene_id": best.id,
        "cloud_cover_pct": float(best.properties.get("eo:cloud_cover", 0.0)),
        "rgb_image": rgb_u8,
        "ndvi_array": spec["ndvi"],
        "ndwi_array": spec["ndwi"],
        "ndvi_mean": spec["ndvi_mean"],
        "ndvi_std": spec["ndvi_std"],
        "ndwi_mean": spec["ndwi_mean"],
        "ndvi_anomaly_delta": spec["ndvi_anomaly_delta"],
        "patch_extent_posgar": (
            patch_bbox_posgar[0],
            patch_bbox_posgar[2],
            patch_bbox_posgar[1],
            patch_bbox_posgar[3],
        ),
    }


def _deg2tile_float(lon_deg: float, lat_deg: float, zoom: int) -> Tuple[float, float]:
    lat_rad = math.radians(lat_deg)
    n = 2.0 ** zoom
    xtile = (lon_deg + 180.0) / 360.0 * n
    ytile = (1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n
    return xtile, ytile


def _fetch_xyz_rgb_chip(
    patch_bbox_wgs84: Tuple[float, float, float, float],
    zoom: int = 17,
) -> Optional[np.ndarray]:
    """Descarga entre 1 y 9 teselas XYZ (256x256) y recorta al parche respetando `max_optical_chip_px`."""
    from PIL import Image

    min_lon, min_lat, max_lon, max_lat = patch_bbox_wgs84
    x0_f, y1_f = _deg2tile_float(min_lon, min_lat, zoom)
    x1_f, y0_f = _deg2tile_float(max_lon, max_lat, zoom)

    x_min, x_max = int(math.floor(x0_f)), int(math.floor(x1_f))
    y_min, y_max = int(math.floor(y0_f)), int(math.floor(y1_f))

    # Tope de seguridad de red: máximo 3x3 teselas
    if (x_max - x_min + 1) * (y_max - y_min + 1) > 9:
        if zoom > 15:
            return _fetch_xyz_rgb_chip(patch_bbox_wgs84, zoom=zoom - 1)
        return None

    tile_size = 256
    mosaic = np.zeros(((y_max - y_min + 1) * tile_size, (x_max - x_min + 1) * tile_size, 3), dtype=np.uint8)

    with httpx.Client(timeout=min(10.0, settings.http_timeout_seconds)) as client:
        for ty in range(y_min, y_max + 1):
            for tx in range(x_min, x_max + 1):
                url = settings.xyz_tile_url.format(z=zoom, x=tx, y=ty)
                resp = client.get(url)
                resp.raise_for_status()
                img = Image.open(io.BytesIO(resp.content)).convert("RGB")
                ox = (tx - x_min) * tile_size
                oy = (ty - y_min) * tile_size
                mosaic[oy : oy + tile_size, ox : ox + tile_size] = np.asarray(img, dtype=np.uint8)

    px0 = max(0, int(round((x0_f - x_min) * tile_size)))
    px1 = min(mosaic.shape[1], int(round((x1_f - x_min) * tile_size)))
    py0 = max(0, int(round((y0_f - y_min) * tile_size)))
    py1 = min(mosaic.shape[0], int(round((y1_f - y_min) * tile_size)))
    if px1 <= px0 + 4 or py1 <= py0 + 4:
        return cap_rgb_chip_size(mosaic)

    crop = mosaic[py0:py1, px0:px1]
    return cap_rgb_chip_size(crop)


def fetch_candidate_optical_context(
    candidate_id: str,
    centroid_wgs84: Sequence[float],
    bbox_posgar: Sequence[float],
    crs_epsg: int,
    out_dir: Optional[Path] = None,
    provider: Optional[str] = None,
    geometry_wgs84: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Obtiene el contexto óptico/espectral acotado exclusivamente al parche de un candidato inédito.

    Retorna `None` si `provider == "none"` o si la red falla (degradación elegante).
    """
    eff_provider = (provider or settings.optical_provider).lower().strip()
    if eff_provider == "none":
        return None

    patch_bbox_posgar, patch_bbox_wgs84 = _posgar_patch_to_wgs84_bbox(
        bbox_posgar=bbox_posgar,
        crs_epsg=crs_epsg,
        buffer_m=settings.optical_buffer_m,
    )

    result: Optional[Dict[str, Any]] = None

    if eff_provider in {"sentinel2_stac", "xyz_tiles", "gee"}:
        # 1. Intentar índices espectrales Sentinel-2 (NDVI/NDWI) cuando corresponde
        if eff_provider == "sentinel2_stac":
            try:
                result = _fetch_sentinel2_stac_patch(
                    centroid_wgs84=centroid_wgs84,
                    patch_bbox_wgs84=patch_bbox_wgs84,
                    patch_bbox_posgar=patch_bbox_posgar,
                    crs_epsg=crs_epsg,
                    geometry_wgs84=geometry_wgs84,
                )
            except Exception as exc:
                logger.debug("Sentinel-2 STAC falló para %s: %s", candidate_id, exc)

        # 2. Intentar chip RGB de alta resolución (XYZ / Esri / Argenmap) para el Panel 5
        try:
            xyz_rgb = _fetch_xyz_rgb_chip(patch_bbox_wgs84)
            if xyz_rgb is not None:
                if result is None:
                    result = {
                        "optical_provider_used": eff_provider if eff_provider != "sentinel2_stac" else "xyz_tiles",
                        "rgb_image": xyz_rgb,
                        "ndvi_array": None,
                        "ndwi_array": None,
                        "ndvi_mean": None,
                        "ndvi_std": None,
                        "ndwi_mean": None,
                        "ndvi_anomaly_delta": None,
                        "patch_extent_posgar": (
                            patch_bbox_posgar[0],
                            patch_bbox_posgar[2],
                            patch_bbox_posgar[1],
                            patch_bbox_posgar[3],
                        ),
                    }
                else:
                    # Enriquecer Sentinel-2 con RGB sub-métrico para el Panel 5
                    result["rgb_image"] = xyz_rgb
        except Exception as exc:
            logger.debug("Chip XYZ RGB falló para %s: %s", candidate_id, exc)

    if result is not None and out_dir is not None and result.get("rgb_image") is not None:
        try:
            from PIL import Image

            out_dir.mkdir(parents=True, exist_ok=True)
            chip_path = out_dir / f"{candidate_id}_optical_rgb.png"
            Image.fromarray(result["rgb_image"]).save(chip_path, optimize=True)
            result["rgb_chip_path"] = str(chip_path)
        except Exception:
            pass

    return result
