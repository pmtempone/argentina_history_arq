"""Gestión de proyecciones cartográficas y reproyección automática a POSGAR 2007 (Argentina)."""

from pathlib import Path
from typing import Any, Dict, Union

import numpy as np
import rasterio
import shapely
from pyproj import CRS, Transformer
from rasterio.warp import Resampling, calculate_default_transform, reproject
from shapely.geometry import mapping, shape

from src.config import POSGAR_2007_EPSG, WGS84_EPSG


def get_posgar_faja(lon: float) -> int:
    """Determina el código EPSG de la faja POSGAR 2007 según la longitud geográfica en Argentina.

    Las fajas Gauss-Krüger de POSGAR 2007 tienen meridianos centrales cada 3 grados:
    - Faja 1 (-72°): lon < -70.5°          -> EPSG:5343
    - Faja 2 (-69°): -70.5° <= lon < -67.5° -> EPSG:5344
    - Faja 3 (-66°): -67.5° <= lon < -64.5° -> EPSG:5345
    - Faja 4 (-63°): -64.5° <= lon < -61.5° -> EPSG:5346
    - Faja 5 (-60°): -61.5° <= lon < -58.5° -> EPSG:5347
    - Faja 6 (-57°): -58.5° <= lon < -55.5° -> EPSG:5348
    - Faja 7 (-54°): lon >= -55.5°         -> EPSG:5349

    Args:
        lon: Longitud geográfica en grados decimales (WGS84, negativa al oeste).

    Returns:
        Código EPSG entero correspondiente a la faja POSGAR 2007 (5343 a 5349).
    """
    if lon < -70.5:
        faja = 1
    elif lon < -67.5:
        faja = 2
    elif lon < -64.5:
        faja = 3
    elif lon < -61.5:
        faja = 4
    elif lon < -58.5:
        faja = 5
    elif lon < -55.5:
        faja = 6
    else:
        faja = 7
    return POSGAR_2007_EPSG[faja]


def is_metric_crs(crs_input: Union[str, int, CRS, rasterio.crs.CRS]) -> bool:
    """Verifica si un sistema de referencia de coordenadas utiliza unidades lineales métricas.

    Args:
        crs_input: Representación del CRS (código EPSG, cadena WKT/PROJ o instancia CRS).

    Returns:
        True si el CRS es proyectado y sus ejes están en metros; False si es geográfico.
    """
    proj_crs = CRS.from_user_input(crs_input)
    if proj_crs.is_geographic:
        return False
    if proj_crs.is_projected:
        axis_info = proj_crs.axis_info
        if axis_info and "metre" in axis_info[0].unit_name.lower() or "meter" in axis_info[0].unit_name.lower():
            return True
    return False


def ensure_metric_crs(src_raster_path: Union[str, Path], out_raster_path: Union[str, Path]) -> str:
    """Garantiza que un raster se encuentre en una proyección métrica POSGAR 2007.

    Si el raster de entrada ya está en un CRS proyectado en metros (ej. POSGAR 2007 o UTM Sur),
    retorna directamente la ruta original (o copia si se solicita una ruta distinta y no existe).
    Si el raster de entrada está en coordenadas geográficas (grados, ej. EPSG:4326), detecta
    automáticamente la faja POSGAR 2007 a partir de la longitud de su centroide y lo reproyecta
    preservando valores NoData como np.nan / nodata explícito.

    Args:
        src_raster_path: Ruta al archivo GeoTIFF de entrada.
        out_raster_path: Ruta donde se escribirá el GeoTIFF reproyectado si fuera necesario.

    Returns:
        Ruta como string al archivo raster en sistema métrico lista para operar.
    """
    src_path = Path(src_raster_path)
    dst_path = Path(out_raster_path)

    with rasterio.open(src_path) as src:
        if src.crs is None:
            raise ValueError(f"El raster '{src_path}' no posee un CRS definido.")

        if is_metric_crs(src.crs):
            return str(src_path)

        # El raster está en coordenadas geográficas (grados): calcular centroide en WGS84
        bounds = src.bounds
        center_lon = (bounds.left + bounds.right) / 2.0
        center_lat = (bounds.bottom + bounds.top) / 2.0

        src_proj = CRS.from_user_input(src.crs)
        if src_proj.to_epsg() != WGS84_EPSG:
            transformer_to_wgs = Transformer.from_crs(src_proj, CRS.from_epsg(WGS84_EPSG), always_xy=True)
            center_lon, center_lat = transformer_to_wgs.transform(center_lon, center_lat)

        target_epsg = get_posgar_faja(center_lon)
        dst_crs = rasterio.crs.CRS.from_epsg(target_epsg)

        transform, width, height = calculate_default_transform(
            src.crs, dst_crs, src.width, src.height, *src.bounds
        )

        nodata_val = src.nodata if src.nodata is not None else -9999.0
        kwargs = src.meta.copy()
        kwargs.update(
            {
                "crs": dst_crs,
                "transform": transform,
                "width": width,
                "height": height,
                "dtype": "float32",
                "nodata": nodata_val,
            }
        )

        dst_path.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(dst_path, "w", **kwargs) as dst:
            for band_idx in range(1, src.count + 1):
                src_band = src.read(band_idx).astype(np.float32)
                if src.nodata is not None:
                    src_band[np.isclose(src_band, src.nodata)] = nodata_val
                dst_band = np.full((height, width), nodata_val, dtype=np.float32)
                reproject(
                    source=src_band,
                    destination=dst_band,
                    src_transform=src.transform,
                    src_crs=src.crs,
                    src_nodata=nodata_val,
                    dst_transform=transform,
                    dst_crs=dst_crs,
                    dst_nodata=nodata_val,
                    resampling=Resampling.bilinear,
                )
                dst.write(dst_band, band_idx)

    return str(dst_path)


def reproject_geometry(geom: Dict[str, Any], from_crs: str, to_crs: str = "EPSG:4326") -> Dict[str, Any]:
    """Reproyecta un diccionario GeoJSON de geometría entre dos sistemas de coordenadas.

    Siempre utiliza el orden de ejes (X/Longitud, Y/Latitud) mediante `always_xy=True`.

    Args:
        geom: Diccionario con estructura GeoJSON Geometry (ej. Polygon, Point, MultiPolygon).
        from_crs: CRS de origen (ej. 'EPSG:5344').
        to_crs: CRS de destino (por defecto 'EPSG:4326' para salidas GeoJSON estándar).

    Returns:
        Diccionario GeoJSON con las coordenadas reproyectadas.
    """
    src_crs_obj = CRS.from_user_input(from_crs)
    dst_crs_obj = CRS.from_user_input(to_crs)

    if src_crs_obj == dst_crs_obj:
        return geom

    transformer = Transformer.from_crs(src_crs_obj, dst_crs_obj, always_xy=True)
    shapely_geom = shape(geom)
    reprojected_shapely = shapely.transform(
        shapely_geom,
        lambda coords: np.column_stack(transformer.transform(coords[:, 0], coords[:, 1])),
    )
    return dict(mapping(reprojected_shapely))
