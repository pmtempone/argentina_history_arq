"""Modelos de relieve local (SLRM) y pendiente (Slope) con tratamiento estricto de NoData."""

from pathlib import Path
from typing import Dict, Union

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


def compute_relief_pipeline(
    dtm_path: Union[str, Path],
    out_dir: Union[str, Path],
    radius_m: float = 10.0,
) -> ReliefResult:
    """Ejecuta el pipeline completo de modelos de relieve (SLRM + Slope) y calcula estadísticas."""
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

    return ReliefResult(
        status="success",
        slrm_path=slrm_path,
        slope_path=slope_path,
        stats_dict=stats_dict,
    )
