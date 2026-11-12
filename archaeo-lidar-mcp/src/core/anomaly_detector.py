"""Detección geométrica de anomalías microtopográficas con OpenCV y clustering espacial cKDTree."""

from pathlib import Path
from typing import Any, Dict, List, Tuple, Union

import cv2
import numpy as np
import rasterio
from scipy.spatial import cKDTree
from shapely.geometry import Polygon, mapping

from src.core.crs_manager import ensure_metric_crs, reproject_geometry
from src.schemas import AnomalyFeature, AnomalyTypeLiteral


def _read_raster_with_nan(path: Path) -> Tuple[np.ndarray, rasterio.Affine, str, float]:
    """Lee un raster convirtiendo NoData a np.nan y devuelve matriz, transform, CRS string y área de píxel."""
    with rasterio.open(path) as src:
        arr = src.read(1).astype(np.float32)
        if src.nodata is not None:
            if np.isnan(src.nodata):
                arr[np.isnan(arr)] = np.nan
            else:
                arr[np.isclose(arr, float(src.nodata)) | (arr <= -9000.0)] = np.nan
        else:
            arr[arr <= -9000.0] = np.nan

        transform = src.transform
        crs_str = src.crs.to_string() if src.crs else "EPSG:5344"
        res_x = float(abs(transform.a))
        res_y = float(abs(transform.e))
        pixel_area_m2 = res_x * res_y
    return arr, transform, crs_str, pixel_area_m2


def _classify_contour_morphology(
    rectangularity: float,
    circularity: float,
    aspect_ratio: float,
    num_vertices: int,
) -> Tuple[AnomalyTypeLiteral, float]:
    """Clasifica la morfología de un contorno arqueológico según sus descriptores geométricos.

    Args:
        rectangularity: Relación entre el área del contorno y el área de su caja mínima rotada [0-1].
        circularity: Índice isoperimétrico `4 * pi * Area / Perimetro^2` [0-1].
        aspect_ratio: Relación largo/ancho de la caja mínima rotada (>= 1.0).
        num_vertices: Cantidad de vértices de la aproximación poligonal (`approxPolyDP`).

    Returns:
        Tupla `(anomaly_type, confidence)`.
    """
    # 1. Terraza lineal o muro largo: alta elongación
    if aspect_ratio >= 3.5:
        conf = min(0.95, 0.65 + 0.05 * min(aspect_ratio - 3.5, 5.0))
        return "terraza_lineal", round(float(conf), 3)

    # 2. Estructura circular (chenque, corral circular, torreón): alta circularidad y baja elongación
    if circularity >= 0.76 and aspect_ratio <= 1.45 and rectangularity < 0.86:
        conf = min(0.98, 0.60 + 0.38 * circularity)
        return "estructura_circular", round(float(conf), 3)

    # 3. Recinto ortogonal (pirca cuadrangular/rectangular, cancha, kallanka): alta rectangularidad
    if rectangularity >= 0.80 or (4 <= num_vertices <= 6 and rectangularity >= 0.72):
        conf = min(0.98, 0.55 + 0.43 * rectangularity)
        return "recinto_ortogonal", round(float(conf), 3)

    # Fallback basado en el descriptor dominante
    if circularity > rectangularity and aspect_ratio < 1.5:
        conf = max(0.50, min(0.90, 0.50 + 0.35 * circularity))
        return "estructura_circular", round(float(conf), 3)

    conf = max(0.50, min(0.90, 0.50 + 0.35 * rectangularity))
    return "recinto_ortogonal", round(float(conf), 3)


def detect_anomalies(
    slrm_path: Union[str, Path],
    slope_path: Union[str, Path],
    min_area: float = 12.0,
    max_area: float = 6000.0,
    min_dz: float = 0.15,
    max_slope_deg: float = 35.0,
) -> Dict[str, Any]:
    """Detecta estructuras arqueológicas en modelos SLRM y Slope usando OpenCV y clustering espacial.

    Pasos del algoritmo:
    1. Verifica que `slrm_path` y `slope_path` estén en proyección métrica POSGAR 2007 y reemplaza
       valores `nodata` con `np.nan`.
    2. Aísla micro-elevaciones positivas en el rango `[0.15 m, 3.0 m]` y enmascara pendientes
       naturales abruptas (`> 35°`).
    3. Aplica filtro bilateral (`cv2.bilateralFilter`) para preservar bordes de muros reduciendo ruido,
       combina umbral adaptativo (`cv2.adaptiveThreshold`) con la máscara de rango microtopográfico y
       aplica clausura morfológica (`cv2.MORPH_CLOSE`).
    4. Extrae contornos externos (`cv2.findContours`), calcula aproximación poligonal (`approxPolyDP`),
       área métrica real en $\text{m}^2$, rectangularidad, circularidad y relación de aspecto.
    5. Clasifica cada estructura en `recinto_ortogonal`, `estructura_circular` o `terraza_lineal`.
    6. Ejecuta clustering espacial con `scipy.spatial.cKDTree` para identificar complejos arquitectónicos
       (estructuras a menos de 80 m entre sí).
    7. Reproyecta los polígonos y centroides a `EPSG:4326` (WGS84) y retorna un GeoJSON `FeatureCollection`.

    Args:
        slrm_path: Ruta al GeoTIFF del Simple Local Relief Model.
        slope_path: Ruta al GeoTIFF de pendiente en grados.
        min_area: Área mínima en metros cuadrados para considerar una anomalía (por defecto 12.0 m²).
        max_area: Área máxima en metros cuadrados para considerar una anomalía (por defecto 6000.0 m²).

    Returns:
        Diccionario GeoJSON `FeatureCollection` con las anomalías validadas y metadatos de agrupamiento.
    """
    src_slrm = Path(slrm_path)
    src_slope = Path(slope_path)

    metric_slrm = Path(ensure_metric_crs(src_slrm, src_slrm.parent / f"{src_slrm.stem}_posgar.tif"))
    metric_slope = Path(ensure_metric_crs(src_slope, src_slope.parent / f"{src_slope.stem}_posgar.tif"))

    slrm, transform, crs_str, pixel_area_m2 = _read_raster_with_nan(metric_slrm)
    slope, _, _, _ = _read_raster_with_nan(metric_slope)

    valid_mask = (~np.isnan(slrm)) & (~np.isnan(slope))

    # Normalizar SLRM en el rango de interés [0.0 m, 3.0 m] a [0, 255] uint8 ignorando NaNs
    slrm_clean = np.where(valid_mask, np.clip(slrm, 0.0, 3.0), 0.0).astype(np.float32)
    slrm_u8 = np.clip((slrm_clean / 3.0) * 255.0, 0, 255).astype(np.uint8)

    # Filtro bilateral sobre imagen uint8 (preserva bordes de pircas y montículos)
    filtered_u8 = cv2.bilateralFilter(slrm_u8, d=7, sigmaColor=35, sigmaSpace=35)
    filtered_slrm = (filtered_u8.astype(np.float32) / 255.0) * 3.0

    # Umbral adaptativo sobre la imagen filtrada + condición estricta de microelevación [0.15m, 3.0m] y pendiente <= 35°
    adaptive_bin = cv2.adaptiveThreshold(
        filtered_u8,
        maxValue=255,
        adaptiveMethod=cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        thresholdType=cv2.THRESH_BINARY,
        blockSize=31,
        C=-2,
    )

    elevation_mask = (filtered_slrm >= min_dz) & (filtered_slrm <= 3.0) & (slrm >= min_dz) & (slrm <= 3.0)
    slope_mask = slope <= max_slope_deg
    combined_mask = np.where(
        valid_mask & elevation_mask & slope_mask & (adaptive_bin > 0),
        255,
        0,
    ).astype(np.uint8)

    # Clausura morfológica suave para consolidar muros contiguos sin distorsionar el área
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    closed_mask = cv2.morphologyEx(combined_mask, cv2.MORPH_CLOSE, kernel, iterations=1)

    contours, _ = cv2.findContours(closed_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)

    raw_candidates: List[Dict[str, Any]] = []
    res_x = float(abs(transform.a))
    res_y = float(abs(transform.e))

    for idx, cnt in enumerate(contours, start=1):
        area_px = float(cv2.contourArea(cnt))
        if area_px <= 0.0:
            continue

        # Corrección de medio píxel en bordes discretizados: en grillas raster, cv2.contourArea mide
        # el polígono que pasa por los centros de los píxeles del borde, subestimando en ~0.5 * perímetro_px.
        perim_px = float(cv2.arcLength(cnt, True))
        effective_area_px = area_px + 0.5 * perim_px
        area_m2 = effective_area_px * pixel_area_m2

        if area_m2 < min_area or area_m2 > max_area:
            continue

        # Caja mínima rotada en píxeles
        rect = cv2.minAreaRect(cnt)
        (_, _), (w_px, h_px), _ = rect
        if w_px <= 1e-3 or h_px <= 1e-3:
            continue

        box_area_px = float((w_px + 1.0) * (h_px + 1.0))
        rectangularity = float(np.clip(effective_area_px / max(box_area_px, 1e-6), 0.0, 1.0))

        # Circularidad isoperimétrica 4 * pi * A / P^2
        if perim_px <= 1e-3:
            continue
        circularity = float(np.clip((4.0 * np.pi * effective_area_px) / (perim_px * perim_px), 0.0, 1.2))

        major_side = max(w_px * res_x, h_px * res_y)
        minor_side = max(1e-3, min(w_px * res_x, h_px * res_y))
        aspect_ratio = float(major_side / minor_side)

        # Aproximación poligonal approxPolyDP
        epsilon = 0.025 * perim_px
        approx = cv2.approxPolyDP(cnt, epsilon, True)
        num_vertices = len(approx)

        anomaly_type, confidence = _classify_contour_morphology(
            rectangularity=rectangularity,
            circularity=circularity,
            aspect_ratio=aspect_ratio,
            num_vertices=num_vertices,
        )

        # Calcular elevación media dentro del contorno
        cnt_mask = np.zeros(slrm.shape, dtype=np.uint8)
        cv2.drawContours(cnt_mask, [cnt], -1, 1, thickness=cv2.FILLED)
        vals = slrm[(cnt_mask == 1) & valid_mask]
        mean_elev_m = float(np.mean(vals)) if vals.size > 0 else 0.0

        # Transformar coordenadas de píxel (col, row) a coordenadas métricas POSGAR 2007 (X, Y)
        pts_px = cnt[:, 0, :]  # shape (N, 2) -> (col, row)
        coords_metric: List[Tuple[float, float]] = []
        for col_i, row_i in pts_px:
            x_m, y_m = rasterio.transform.xy(transform, float(row_i), float(col_i), offset="center")
            coords_metric.append((float(x_m), float(y_m)))

        if len(coords_metric) < 3:
            continue
        if coords_metric[0] != coords_metric[-1]:
            coords_metric.append(coords_metric[0])

        poly_metric = Polygon(coords_metric)
        if not poly_metric.is_valid:
            poly_metric = poly_metric.buffer(0)

        centroid_metric = (float(poly_metric.centroid.x), float(poly_metric.centroid.y))
        geom_wgs84 = reproject_geometry(dict(mapping(poly_metric)), from_crs=crs_str, to_crs="EPSG:4326")
        centroid_pt_wgs84 = reproject_geometry(
            {"type": "Point", "coordinates": [centroid_metric[0], centroid_metric[1]]},
            from_crs=crs_str,
            to_crs="EPSG:4326",
        )
        lon_wgs, lat_wgs = (
            float(centroid_pt_wgs84["coordinates"][0]),
            float(centroid_pt_wgs84["coordinates"][1]),
        )

        raw_candidates.append(
            {
                "id": f"ARQ-{idx:04d}",
                "anomaly_type": anomaly_type,
                "confidence": confidence,
                "area_m2": round(area_m2, 2),
                "rectangularity": round(rectangularity, 4),
                "circularity": round(circularity, 4),
                "aspect_ratio": round(aspect_ratio, 3),
                "mean_elevation_m": round(mean_elev_m, 3),
                "centroid_metric": centroid_metric,
                "centroid_wgs84": (round(lon_wgs, 6), round(lat_wgs, 6)),
                "geometry_geojson": geom_wgs84,
            }
        )

    # Clustering espacial con cKDTree para detectar complejos arquitectónicos (< 80 m)
    cluster_assignments: Dict[int, List[int]] = {}
    if len(raw_candidates) >= 2:
        centroids_arr = np.array([c["centroid_metric"] for c in raw_candidates], dtype=np.float64)
        tree = cKDTree(centroids_arr)
        neighbors_list = tree.query_ball_tree(tree, r=80.0)
        for i, neighbors in enumerate(neighbors_list):
            if len(neighbors) > 1:
                cluster_assignments[i] = neighbors

    features: List[Dict[str, Any]] = []
    for i, cand in enumerate(raw_candidates):
        in_complex = i in cluster_assignments
        neighbors_ids = [raw_candidates[n]["id"] for n in cluster_assignments.get(i, []) if n != i]

        # Validar mediante el esquema Pydantic AnomalyFeature
        validated_feat = AnomalyFeature(
            id=cand["id"],
            anomaly_type=cand["anomaly_type"],
            confidence=cand["confidence"],
            area_m2=cand["area_m2"],
            rectangularity=cand["rectangularity"],
            circularity=cand["circularity"],
            mean_elevation_m=cand["mean_elevation_m"],
            centroid_wgs84=cand["centroid_wgs84"],
            geometry_geojson=cand["geometry_geojson"],
        )

        feature_dict: Dict[str, Any] = {
            "type": "Feature",
            "id": validated_feat.id,
            "geometry": validated_feat.geometry_geojson,
            "properties": {
                "id": validated_feat.id,
                "anomaly_type": validated_feat.anomaly_type,
                "confidence": validated_feat.confidence,
                "area_m2": validated_feat.area_m2,
                "rectangularity": validated_feat.rectangularity,
                "circularity": validated_feat.circularity,
                "aspect_ratio": cand["aspect_ratio"],
                "mean_elevation_m": validated_feat.mean_elevation_m,
                "centroid_wgs84": list(validated_feat.centroid_wgs84),
                "is_architectural_complex": in_complex,
                "complex_group_type": "complejo_agrupado" if in_complex else validated_feat.anomaly_type,
                "cluster_neighbors": neighbors_ids,
            },
        }
        features.append(feature_dict)

    return {
        "type": "FeatureCollection",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
        "metadata": {
            "source_crs": crs_str,
            "total_detected": len(features),
            "architectural_complex_members": len(cluster_assignments),
        },
        "features": features,
    }
