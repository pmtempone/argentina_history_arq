"""Procesamiento de nubes de puntos LiDAR (.las/.laz) a DTM mediante PDAL y GDAL."""

import json
from pathlib import Path
from typing import Any, Dict, List, Union

import numpy as np
import rasterio
from pyproj import CRS, Transformer

from src.core.crs_manager import ensure_metric_crs, get_posgar_faja, is_metric_crs
from src.schemas import DTMResult

try:
    import pdal

    HAS_PDAL = True
except ImportError:
    pdal = None  # type: ignore[assignment]
    HAS_PDAL = False


def _inspect_las_metadata(las_path: Path) -> Dict[str, Any]:
    """Inspecciona metadatos básicos e histograma de clasificación en un archivo LAS/LAZ."""
    if not HAS_PDAL:
        raise RuntimeError(
            "El módulo Python 'pdal' no está disponible en este entorno. "
            "Ejecute dentro del contenedor Docker (conda-forge) o instale python-pdal."
        )

    info_pipeline_def: List[Dict[str, Any]] = [
        {"type": "readers.las", "filename": str(las_path)},
        {"type": "filters.stats", "dimensions": "Classification", "enumerate": "Classification"},
    ]
    pipeline = pdal.Pipeline(json.dumps(info_pipeline_def))
    pipeline.execute()
    metadata: Dict[str, Any] = json.loads(pipeline.metadata)
    return metadata


def _has_ground_classification(metadata: Dict[str, Any]) -> bool:
    """Determina si la nube de puntos ya cuenta con retornos clasificados como suelo (Clase 2)."""
    try:
        stats_node = metadata.get("metadata", {}).get("filters.stats", {})
        bbox_stats = stats_node.get("statistic", [])
        for stat in bbox_stats:
            if stat.get("name") == "Classification":
                values = stat.get("values", {})
                if "2" in values or 2 in values:
                    return int(values.get("2", values.get(2, 0))) > 0
    except Exception:
        pass
    return False


def _detect_las_target_epsg(metadata: Dict[str, Any]) -> int:
    """Detecta el código EPSG métrico POSGAR 2007 para la nube LiDAR."""
    readers_meta = metadata.get("metadata", {}).get("readers.las", {})
    srs_wkt = readers_meta.get("spatialreference", "") or readers_meta.get("comp_spatialreference", "")
    minx = float(readers_meta.get("minx", -66.0))
    maxx = float(readers_meta.get("maxx", -66.0))
    miny = float(readers_meta.get("miny", -25.0))
    maxy = float(readers_meta.get("maxy", -25.0))
    center_x = (minx + maxx) / 2.0
    center_y = (miny + maxy) / 2.0

    if srs_wkt:
        try:
            crs_obj = CRS.from_user_input(srs_wkt)
            if is_metric_crs(crs_obj):
                epsg = crs_obj.to_epsg()
                if epsg is not None:
                    return int(epsg)
            # Si es geográfico, obtener longitud en WGS84 y asignar faja POSGAR 2007
            if crs_obj.to_epsg() != 4326:
                transformer = Transformer.from_crs(crs_obj, CRS.from_epsg(4326), always_xy=True)
                center_x, _ = transformer.transform(center_x, center_y)
            return get_posgar_faja(center_x)
        except Exception:
            pass

    # Heurística por rango de coordenadas si el encabezado LAS carece de WKT válido
    if -80.0 <= center_x <= -50.0 and -60.0 <= center_y <= -20.0:
        return get_posgar_faja(center_x)
    # Por defecto NOA Oeste (Faja 2 - EPSG:5344) si ya viene en metros sin EPSG explícito
    return 5344


def lidar_to_dtm(
    las_path: Union[str, Path],
    out_dtm_path: Union[str, Path],
    resolution: float = 0.5,
    force_smrf: bool = False,
) -> DTMResult:
    """Procesa una nube de puntos LiDAR (.las/.laz) para generar un DTM bare-earth en POSGAR 2007.

    Si los puntos no poseen clasificación de suelo (ASPRS Clase 2) o si `force_smrf=True`,
    ejecuta automáticamente el filtro Simple Morphological Filter (`filters.smrf`) calibrado
    para vegetación arbustiva y monte argentino (`slope=0.2`, `window=16.0`, `threshold=0.45`,
    `scalar=1.25`). Luego filtra retornos `Classification[2:2]` e interpola la grilla con IDW
    mediante `writers.gdal`.

    Args:
        las_path: Ruta al archivo `.las` o `.laz` de entrada.
        out_dtm_path: Ruta donde se guardará el GeoTIFF del DTM resultante.
        resolution: Tamaño de celda de salida en metros (por defecto 0.5 m).
        force_smrf: Si es True, recalcula la clasificación de suelo con SMRF aunque ya exista Clase 2.

    Returns:
        Instancia de `DTMResult` con la ruta, EPSG, resolución, extensión y conteo de puntos.
    """
    src_las = Path(las_path)
    dst_dtm = Path(out_dtm_path)
    dst_dtm.parent.mkdir(parents=True, exist_ok=True)

    if not src_las.exists():
        raise FileNotFoundError(f"No se encontró el archivo LiDAR de entrada: {src_las}")

    if not HAS_PDAL:
        raise RuntimeError(
            "PDAL Python bindings no están instalados. Ejecute dentro del entorno conda-forge / Docker."
        )

    metadata = _inspect_las_metadata(src_las)
    has_ground = _has_ground_classification(metadata)
    target_epsg = _detect_las_target_epsg(metadata)

    readers_meta = metadata.get("metadata", {}).get("readers.las", {})
    srs_wkt = readers_meta.get("spatialreference", "") or readers_meta.get("comp_spatialreference", "")

    pipeline_stages: List[Dict[str, Any]] = [
        {"type": "readers.las", "filename": str(src_las)},
    ]

    # Reproyectar nube de puntos a POSGAR 2007 si viene en coordenadas geográficas
    if srs_wkt:
        try:
            in_crs = CRS.from_user_input(srs_wkt)
            if not is_metric_crs(in_crs):
                pipeline_stages.append(
                    {
                        "type": "filters.reprojection",
                        "out_srs": f"EPSG:{target_epsg}",
                    }
                )
        except Exception:
            pass

    # Aplicar filtro morfológico SMRF si no hay puntos Clase 2 o si se fuerza
    if force_smrf or not has_ground:
        pipeline_stages.append(
            {
                "type": "filters.smrf",
                "slope": 0.2,
                "window": 16.0,
                "threshold": 0.45,
                "scalar": 1.25,
            }
        )

    # Conservar exclusivamente retornos de suelo desnudo (ASPRS Clase 2)
    pipeline_stages.append(
        {
            "type": "filters.range",
            "limits": "Classification[2:2]",
        }
    )

    # Exportar DTM interpolado con IDW a GeoTIFF Float32
    pipeline_stages.append(
        {
            "type": "writers.gdal",
            "filename": str(dst_dtm),
            "gdaldriver": "GTiff",
            "output_type": "idw",
            "resolution": float(resolution),
            "radius": float(resolution) * 2.8284,
            "data_type": "float32",
            "nodata": -9999.0,
            "override_srs": f"EPSG:{target_epsg}",
        }
    )

    pipeline = pdal.Pipeline(json.dumps(pipeline_stages))
    point_count: int = int(pipeline.execute())

    # Garantizar proyección métrica POSGAR 2007 en el GeoTIFF resultante
    verified_dtm_path = ensure_metric_crs(dst_dtm, dst_dtm)

    with rasterio.open(verified_dtm_path) as src:
        epsg_code = src.crs.to_epsg() if src.crs else target_epsg
        b = src.bounds
        res_m = float(abs(src.transform.a))

    return DTMResult(
        status="success",
        dtm_path=str(verified_dtm_path),
        crs_epsg=int(epsg_code or target_epsg),
        resolution_m=res_m,
        bounds=(float(b.left), float(b.bottom), float(b.right), float(b.top)),
        point_count=point_count,
    )
