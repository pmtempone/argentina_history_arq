"""Modelos de relieve local (SLRM) y pendiente (Slope) con tratamiento estricto de NoData."""

import json
import math
from pathlib import Path
from typing import Dict, Optional, Tuple, Union

import numpy as np
import rasterio
from scipy.ndimage import gaussian_filter, uniform_filter

from src.core.crs_manager import ensure_metric_crs
from src.schemas import ReliefResult

NODATA_FLOAT32: float = -9999.0


def _read_metric_raster_as_nan(raster_path: Path) -> tuple[np.ndarray, Dict[str, object], float, float]:
    """Lee la banda 1 de un raster métrico convirtiendo valores NoData a np.nan."""
    with rasterio.open(raster_path) as src:
        data = src.read(1).astype(np.float64)
        profile = dict(src.profile)
        nodata = src.nodata
        if nodata is not None:
            if np.isnan(nodata):
                mask = np.isnan(data)
            else:
                mask = np.isclose(data, float(nodata)) | (data <= -9000.0)
            data[mask] = np.nan
        else:
            data[data <= -9000.0] = np.nan

        res_x = float(abs(src.transform.a))
        res_y = float(abs(src.transform.e))
    return data, profile, res_x, res_y


def _nan_aware_trend_surface(data: np.ndarray, radius_px: float, method: str = "gaussian") -> np.ndarray:
    """Calcula una superficie de tendencia suave ignorando celdas np.nan para evitar artefactos de borde.

    Utiliza convolución normalizada por pesos:
        Trend = Filter(V) / Filter(W)
    donde V tiene 0 en los píxeles NaN y W es 1 en píxeles válidos y 0 en NaN.
    """
    valid_mask = ~np.isnan(data)
    filled_data = np.where(valid_mask, data, 0.0)
    weights = valid_mask.astype(np.float64)

    if method == "gaussian":
        sigma = max(1.0, radius_px / 2.0)
        smooth_vals = gaussian_filter(filled_data, sigma=sigma, mode="nearest")
        smooth_weights = gaussian_filter(weights, sigma=sigma, mode="nearest")
    else:
        win_size = max(3, int(round(2 * radius_px + 1)))
        smooth_vals = uniform_filter(filled_data, size=win_size, mode="nearest")
        smooth_weights = uniform_filter(weights, size=win_size, mode="nearest")

    with np.errstate(invalid="ignore", divide="ignore"):
        trend = np.where(smooth_weights > 1e-6, smooth_vals / smooth_weights, np.nan)

    trend[~valid_mask] = np.nan
    return trend


def compute_slrm(
    dtm_path: Union[str, Path],
    out_slrm_path: Union[str, Path],
    radius_m: float = 10.0,
) -> str:
    """Calcula el Simple Local Relief Model (SLRM) sustrayendo la tendencia topográfica local al DTM.

    Garantiza que el raster esté proyectado en POSGAR 2007 (metros), convierte `nodata` a `np.nan`
    antes de aplicar el filtro gaussiano normalizado y exporta `SLRM = DTM - DTM_trend` en Float32.

    Args:
        dtm_path: Ruta al archivo GeoTIFF del DTM de entrada.
        out_slrm_path: Ruta donde se escribirá el GeoTIFF Float32 del SLRM.
        radius_m: Radio del filtro de tendencia local en metros (por defecto 10.0 m).

    Returns:
        Ruta como string al archivo GeoTIFF del SLRM generado.
    """
    src_path = Path(dtm_path)
    dst_path = Path(out_slrm_path)
    dst_path.parent.mkdir(parents=True, exist_ok=True)

    metric_dtm_temp = dst_path.parent / f"{src_path.stem}_metric_posgar.tif"
    metric_dtm_path = Path(ensure_metric_crs(src_path, metric_dtm_temp))

    dtm, profile, res_x, res_y = _read_metric_raster_as_nan(metric_dtm_path)
    mean_res_m = (res_x + res_y) / 2.0
    if mean_res_m <= 0.0:
        raise ValueError(f"Resolución espacial inválida en DTM: {mean_res_m}")

    radius_px = max(2.0, float(radius_m) / mean_res_m)
    trend = _nan_aware_trend_surface(dtm, radius_px=radius_px, method="gaussian")
    slrm = dtm - trend

    out_array = np.where(np.isnan(slrm), NODATA_FLOAT32, slrm).astype(np.float32)
    profile.update(
        {
            "dtype": "float32",
            "count": 1,
            "nodata": NODATA_FLOAT32,
            "compress": "deflate",
        }
    )

    with rasterio.open(dst_path, "w", **profile) as dst:
        dst.write(out_array, 1)

    return str(dst_path)


def compute_slope(
    dtm_path: Union[str, Path],
    out_slope_path: Union[str, Path],
) -> str:
    """Calcula la pendiente topográfica en grados sexagesimales [0° - 90°] a partir de un DTM métrico.

    Convierte `nodata` a `np.nan` antes de calcular el gradiente espacial con `np.gradient`
    escalado por el tamaño real de píxel en metros (`res_y`, `res_x`).

    Args:
        dtm_path: Ruta al archivo GeoTIFF del DTM de entrada.
        out_slope_path: Ruta donde se escribirá el GeoTIFF Float32 de pendiente.

    Returns:
        Ruta como string al archivo GeoTIFF de pendiente generado.
    """
    src_path = Path(dtm_path)
    dst_path = Path(out_slope_path)
    dst_path.parent.mkdir(parents=True, exist_ok=True)

    metric_dtm_temp = dst_path.parent / f"{src_path.stem}_metric_posgar.tif"
    metric_dtm_path = Path(ensure_metric_crs(src_path, metric_dtm_temp))

    dtm, profile, res_x, res_y = _read_metric_raster_as_nan(metric_dtm_path)
    dy, dx = np.gradient(dtm, res_y, res_x)
    slope_rad = np.arctan(np.hypot(dx, dy))
    slope_deg = np.degrees(slope_rad)

    out_array = np.where(np.isnan(slope_deg), NODATA_FLOAT32, slope_deg).astype(np.float32)
    profile.update(
        {
            "dtype": "float32",
            "count": 1,
            "nodata": NODATA_FLOAT32,
            "compress": "deflate",
        }
    )

    with rasterio.open(dst_path, "w", **profile) as dst:
        dst.write(out_array, 1)

    return str(dst_path)


def _shift_no_wrap_nan(arr: np.ndarray, d_row: int, d_col: int) -> np.ndarray:
    """Desplaza un array 2D sin envolver bordes, rellenando fuera de rango con np.nan."""
    h, w = arr.shape
    out = np.full((h, w), np.nan, dtype=np.float64)
    src_r0 = max(0, -d_row)
    src_r1 = min(h, h - d_row) if d_row >= 0 else h
    dst_r0 = max(0, d_row)
    dst_r1 = dst_r0 + (src_r1 - src_r0)

    src_c0 = max(0, -d_col)
    src_c1 = min(w, w - d_col) if d_col >= 0 else w
    dst_c0 = max(0, d_col)
    dst_c1 = dst_c0 + (src_c1 - src_c0)

    if src_r1 > src_r0 and src_c1 > src_c0:
        out[dst_r0:dst_r1, dst_c0:dst_c1] = arr[src_r0:src_r1, src_c0:src_c1]
    return out


def compute_sky_view_factor(
    dtm_path: Union[str, Path],
    out_svf_path: Union[str, Path],
    radius_m: float = 10.0,
    num_directions: int = 16,
) -> str:
    """Calcula el Sky-View Factor (SVF ∈ [0, 1]) NaN-safe según Kokalj & Hesse (2017)."""
    src_path = Path(dtm_path)
    dst_path = Path(out_svf_path)
    dst_path.parent.mkdir(parents=True, exist_ok=True)

    metric_dtm_temp = dst_path.parent / f"{src_path.stem}_metric_posgar.tif"
    metric_dtm_path = Path(ensure_metric_crs(src_path, metric_dtm_temp))

    dtm, profile, res_x, res_y = _read_metric_raster_as_nan(metric_dtm_path)
    mean_res_m = (res_x + res_y) / 2.0
    max_steps = max(2, min(12, int(round(radius_m / max(mean_res_m, 1e-6)))))

    valid_center = ~np.isnan(dtm)
    svf_accum = np.zeros_like(dtm, dtype=np.float64)
    azimuths = np.linspace(0.0, 2.0 * math.pi, num_directions, endpoint=False)

    for theta in azimuths:
        max_horizon = np.zeros_like(dtm, dtype=np.float64)
        for step in range(1, max_steps + 1):
            d_col = int(round(math.cos(theta) * step))
            d_row = int(round(math.sin(theta) * step))
            if d_col == 0 and d_row == 0:
                continue
            dist_m = math.hypot(d_col * res_x, d_row * res_y)
            neighbor = _shift_no_wrap_nan(dtm, d_row=d_row, d_col=d_col)
            angle = np.arctan2(np.maximum(0.0, neighbor - dtm), dist_m)
            valid_angle = np.where(np.isnan(angle), 0.0, angle)
            max_horizon = np.maximum(max_horizon, valid_angle)
        svf_accum += 1.0 - np.sin(max_horizon)

    svf = np.where(valid_center, svf_accum / float(max(1, num_directions)), np.nan)
    out_array = np.where(np.isnan(svf), NODATA_FLOAT32, np.clip(svf, 0.0, 1.0)).astype(np.float32)
    profile.update({"dtype": "float32", "count": 1, "nodata": NODATA_FLOAT32, "compress": "deflate"})
    with rasterio.open(dst_path, "w", **profile) as dst:
        dst.write(out_array, 1)
    return str(dst_path)


def compute_openness(
    dtm_path: Union[str, Path],
    out_pos_openness_path: Union[str, Path],
    out_neg_openness_path: Optional[Union[str, Path]] = None,
    radius_m: float = 10.0,
    num_directions: int = 8,
) -> Tuple[str, Optional[str]]:
    """Calcula Positive Openness y Negative Openness (grados, NaN-safe) según Kokalj & Hesse (2017)."""
    src_path = Path(dtm_path)
    pos_path = Path(out_pos_openness_path)
    pos_path.parent.mkdir(parents=True, exist_ok=True)
    neg_path = Path(out_neg_openness_path) if out_neg_openness_path else None
    if neg_path:
        neg_path.parent.mkdir(parents=True, exist_ok=True)

    metric_dtm_temp = pos_path.parent / f"{src_path.stem}_metric_posgar.tif"
    metric_dtm_path = Path(ensure_metric_crs(src_path, metric_dtm_temp))

    dtm, profile, res_x, res_y = _read_metric_raster_as_nan(metric_dtm_path)
    mean_res_m = (res_x + res_y) / 2.0
    max_steps = max(2, min(12, int(round(radius_m / max(mean_res_m, 1e-6)))))

    valid_center = ~np.isnan(dtm)
    pos_accum = np.zeros_like(dtm, dtype=np.float64)
    neg_accum = np.zeros_like(dtm, dtype=np.float64)
    azimuths = np.linspace(0.0, 2.0 * math.pi, num_directions, endpoint=False)

    for theta in azimuths:
        max_beta = np.full_like(dtm, -math.pi / 2.0, dtype=np.float64)
        min_delta = np.full_like(dtm, math.pi / 2.0, dtype=np.float64)
        has_any_neighbor = np.zeros_like(valid_center, dtype=bool)
        for step in range(1, max_steps + 1):
            d_col = int(round(math.cos(theta) * step))
            d_row = int(round(math.sin(theta) * step))
            if d_col == 0 and d_row == 0:
                continue
            dist_m = math.hypot(d_col * res_x, d_row * res_y)
            neighbor = _shift_no_wrap_nan(dtm, d_row=d_row, d_col=d_col)
            pair_valid = valid_center & ~np.isnan(neighbor)
            elev_angle = np.where(pair_valid, np.arctan2(neighbor - dtm, dist_m), np.nan)
            has_any_neighbor |= pair_valid
            max_beta = np.where(pair_valid, np.maximum(max_beta, elev_angle), max_beta)
            min_delta = np.where(pair_valid, np.minimum(min_delta, elev_angle), min_delta)

        dir_beta = np.where(has_any_neighbor, max_beta, 0.0)
        dir_delta = np.where(has_any_neighbor, min_delta, 0.0)
        pos_accum += 90.0 - np.degrees(dir_beta)
        neg_accum += 90.0 + np.degrees(dir_delta)

    pos_openness = np.where(valid_center, pos_accum / float(max(1, num_directions)), np.nan)
    profile.update({"dtype": "float32", "count": 1, "nodata": NODATA_FLOAT32, "compress": "deflate"})
    out_pos = np.where(np.isnan(pos_openness), NODATA_FLOAT32, np.clip(pos_openness, 0.0, 180.0)).astype(np.float32)
    with rasterio.open(pos_path, "w", **profile) as dst:
        dst.write(out_pos, 1)

    neg_out_str: Optional[str] = None
    if neg_path is not None:
        neg_openness = np.where(valid_center, neg_accum / float(max(1, num_directions)), np.nan)
        out_neg = np.where(np.isnan(neg_openness), NODATA_FLOAT32, np.clip(neg_openness, 0.0, 180.0)).astype(np.float32)
        with rasterio.open(neg_path, "w", **profile) as dst:
            dst.write(out_neg, 1)
        neg_out_str = str(neg_path)

    return str(pos_path), neg_out_str


def compute_relief_pipeline(
    dtm_path: Union[str, Path],
    out_dir: Union[str, Path],
    radius_m: float = 10.0,
    include_svf_openness: bool = False,
) -> ReliefResult:
    """Ejecuta el pipeline completo de modelos de relieve (SLRM + Slope [+ SVF/Openness]) y guarda trazabilidad."""
    src_path = Path(dtm_path)
    target_dir = Path(out_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    slrm_path = compute_slrm(src_path, target_dir / f"{src_path.stem}_slrm.tif", radius_m=radius_m)
    slope_path = compute_slope(src_path, target_dir / f"{src_path.stem}_slope.tif")

    slrm_arr, _, _, _ = _read_metric_raster_as_nan(Path(slrm_path))
    slope_arr, _, _, _ = _read_metric_raster_as_nan(Path(slope_path))

    stats_dict: Dict[str, float] = {
        "slrm_min_m": float(np.nanmin(slrm_arr)) if not np.all(np.isnan(slrm_arr)) else 0.0,
        "slrm_max_m": float(np.nanmax(slrm_arr)) if not np.all(np.isnan(slrm_arr)) else 0.0,
        "slrm_mean_m": float(np.nanmean(slrm_arr)) if not np.all(np.isnan(slrm_arr)) else 0.0,
        "slrm_std_m": float(np.nanstd(slrm_arr)) if not np.all(np.isnan(slrm_arr)) else 0.0,
        "slope_max_deg": float(np.nanmax(slope_arr)) if not np.all(np.isnan(slope_arr)) else 0.0,
        "slope_mean_deg": float(np.nanmean(slope_arr)) if not np.all(np.isnan(slope_arr)) else 0.0,
    }

    svf_path: Optional[str] = None
    pos_openness_path: Optional[str] = None
    neg_openness_path: Optional[str] = None
    if include_svf_openness:
        svf_path = compute_sky_view_factor(src_path, target_dir / f"{src_path.stem}_svf.tif", radius_m=radius_m)
        pos_openness_path, neg_openness_path = compute_openness(
            src_path,
            out_pos_openness_path=target_dir / f"{src_path.stem}_openness_pos.tif",
            out_neg_openness_path=target_dir / f"{src_path.stem}_openness_neg.tif",
            radius_m=radius_m,
        )
        svf_arr, _, _, _ = _read_metric_raster_as_nan(Path(svf_path))
        pos_arr, _, _, _ = _read_metric_raster_as_nan(Path(pos_openness_path))
        neg_arr, _, _, _ = _read_metric_raster_as_nan(Path(neg_openness_path))
        stats_dict["svf_mean"] = float(np.nanmean(svf_arr)) if not np.all(np.isnan(svf_arr)) else 0.0
        stats_dict["pos_openness_mean_deg"] = float(np.nanmean(pos_arr)) if not np.all(np.isnan(pos_arr)) else 0.0
        stats_dict["neg_openness_mean_deg"] = float(np.nanmean(neg_arr)) if not np.all(np.isnan(neg_arr)) else 0.0

    params_json_path = str(target_dir / f"{src_path.stem}_relief_params.json")
    Path(params_json_path).write_text(
        json.dumps(
            {
                "dtm_path": str(src_path),
                "radius_m": float(radius_m),
                "include_svf_openness": bool(include_svf_openness),
                "slrm_path": slrm_path,
                "slope_path": slope_path,
                "svf_path": svf_path,
                "pos_openness_path": pos_openness_path,
                "neg_openness_path": neg_openness_path,
                "stats": stats_dict,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    return ReliefResult(
        status="success",
        slrm_path=slrm_path,
        slope_path=slope_path,
        stats_dict=stats_dict,
        svf_path=svf_path,
        pos_openness_path=pos_openness_path,
        neg_openness_path=neg_openness_path,
        params_json_path=params_json_path,
    )
