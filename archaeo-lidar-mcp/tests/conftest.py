"""Fixtures de terreno sintético en POSGAR 2007 (EPSG:5344) con pirca rectangular y chenque circular."""

from pathlib import Path
from typing import Dict, Any

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin


@pytest.fixture
def synthetic_posgar_dtm(tmp_path: Path) -> Path:
    """Genera un GeoTIFF sintético de 400x400 px (0.5 m/px) en EPSG:5344 (POSGAR 2007 Faja 2).

    Características del terreno sintético:
    - Extensión: 200 m x 200 m (400 x 400 píxeles a 0.5 m/px).
    - Coordenadas de origen en Faja 2 (NOA Oeste, ej. Catamarca/San Juan):
      `west = 2500000.0`, `north = 7000200.0` (`EPSG:5344`).
    - Terreno base colinar suave:
      `z = 2000.0 + 5.0 * sin(x / 50.0) + 5.0 * cos(y / 50.0)`
      donde `x` e `y` son coordenadas métricas locales en `[0, 200]`.
    - Anomalía 1 (Recinto rectangular tipo pirca):
      Dimensiones `14.0 m x 8.0 m` (área teórica = `112.0 m²`), rotado `25°`,
      centrado en `(x0=65.0 m, y0=65.0 m)`, con sobreelevación de `+0.6 m`.
    - Anomalía 2 (Estructura circular tipo corral o chenque):
      Diámetro de `10.0 m` (radio = `5.0 m`, área teórica = `pi * 25 ≈ 78.54 m²`),
      centrado en `(x1=120.0 m, y1=115.0 m)` (distancia ~74 m de la pirca para formar un complejo < 80 m),
      con sobreelevación de `+0.6 m`.
    """
    width = 400
    height = 400
    res = 0.5

    west = 2500000.0
    north = 7000200.0
    transform = from_origin(west, north, res, res)

    # Coordenadas métricas locales del centro de cada celda (0.25 m a 199.75 m)
    cols = (np.arange(width, dtype=np.float64) + 0.5) * res
    rows = (np.arange(height, dtype=np.float64) + 0.5) * res
    xx, yy = np.meshgrid(cols, rows)

    # Superficie topográfica colinar suave
    z = 2000.0 + 5.0 * np.sin(xx / 50.0) + 5.0 * np.cos(yy / 50.0)

    # 1. Inyección de recinto rectangular (14m x 8m) rotado 25° en (65m, 65m)
    cx_rect, cy_rect = 65.0, 65.0
    theta = np.radians(25.0)
    dx_r = xx - cx_rect
    dy_r = yy - cy_rect
    x_rot = dx_r * np.cos(theta) + dy_r * np.sin(theta)
    y_rot = -dx_r * np.sin(theta) + dy_r * np.cos(theta)
    rect_mask = (np.abs(x_rot) <= 7.0) & (np.abs(y_rot) <= 4.0)
    z[rect_mask] += 0.60

    # 2. Inyección de estructura circular (diámetro 10m -> radio 5m) en (120m, 115m)
    cx_circ, cy_circ = 120.0, 115.0
    dist_circ = np.hypot(xx - cx_circ, yy - cy_circ)
    circ_mask = dist_circ <= 5.0
    z[circ_mask] += 0.60

    dtm_path = tmp_path / "synthetic_posgar_faja2_dtm.tif"
    profile: Dict[str, Any] = {
        "driver": "GTiff",
        "height": height,
        "width": width,
        "count": 1,
        "dtype": "float32",
        "crs": rasterio.crs.CRS.from_epsg(5344),
        "transform": transform,
        "nodata": -9999.0,
    }

    with rasterio.open(dtm_path, "w", **profile) as dst:
        dst.write(z.astype(np.float32), 1)

    return dtm_path


@pytest.fixture
def synthetic_posgar_dtm_with_pit(tmp_path: Path) -> Path:
    """Variante del DTM sintético con estructuras positivas y un hundimiento plantado (relieve negativo).

    Mismo terreno base y las mismas dos estructuras positivas que `synthetic_posgar_dtm`
    (pirca rectangular y chenque circular), más:
    - Anomalía 3 (Pozo / patio hundido, relieve negativo):
      Diámetro de `12.0 m` (área teórica = `pi * 36 ≈ 113.10 m²`), centrado en
      `(x2=185.0 m, y2=185.0 m)` (a ~95 m del chenque y ~120 m de la pirca, fuera del
      complejo de < 80 m), con depresión de `-0.6 m`.
    """
    width = 400
    height = 400
    res = 0.5

    west = 2500000.0
    north = 7000200.0
    transform = from_origin(west, north, res, res)

    cols = (np.arange(width, dtype=np.float64) + 0.5) * res
    rows = (np.arange(height, dtype=np.float64) + 0.5) * res
    xx, yy = np.meshgrid(cols, rows)

    z = 2000.0 + 5.0 * np.sin(xx / 50.0) + 5.0 * np.cos(yy / 50.0)

    # 1. Recinto rectangular (14m x 8m) rotado 25° en (65m, 65m)
    cx_rect, cy_rect = 65.0, 65.0
    theta = np.radians(25.0)
    dx_r = xx - cx_rect
    dy_r = yy - cy_rect
    x_rot = dx_r * np.cos(theta) + dy_r * np.sin(theta)
    y_rot = -dx_r * np.sin(theta) + dy_r * np.cos(theta)
    z[(np.abs(x_rot) <= 7.0) & (np.abs(y_rot) <= 4.0)] += 0.60

    # 2. Estructura circular (diámetro 10m) en (120m, 115m)
    z[np.hypot(xx - 120.0, yy - 115.0) <= 5.0] += 0.60

    # 3. Pozo hundido (diámetro 12m) en (185m, 185m), relieve negativo, fuera del complejo (< 80 m)
    z[np.hypot(xx - 185.0, yy - 185.0) <= 6.0] -= 0.60

    dtm_path = tmp_path / "synthetic_posgar_faja2_dtm_pit.tif"
    profile: Dict[str, Any] = {
        "driver": "GTiff",
        "height": height,
        "width": width,
        "count": 1,
        "dtype": "float32",
        "crs": rasterio.crs.CRS.from_epsg(5344),
        "transform": transform,
        "nodata": -9999.0,
    }

    with rasterio.open(dtm_path, "w", **profile) as dst:
        dst.write(z.astype(np.float32), 1)

    return dtm_path
