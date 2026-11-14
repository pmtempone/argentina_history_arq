"""Detección geométrica de anomalías microtopográficas con OpenCV y clustering espacial cKDTree.

El detector opera en doble pase de signo:
- **Relieve positivo** (sobreelevaciones): pircas, recintos, montículos, chenques, terrazas.
- **Relieve negativo** (hundimientos): pozos, casas-pozo, patios hundidos, zanjas y canales.

Esto permite capturar tanto estructuras emergentes como excavadas, con la misma cadena
OpenCV (filtro bilateral + umbral adaptativo + clausura morfológica) aplicada al SLRM
espejado según el signo del pase.
"""

from pathlib import Path
from typing import Any, Dict, List, Tuple, Union

import cv2
import numpy as np
import rasterio
from scipy.spatial import cKDTree
from shapely.geometry import Polygon, mapping

from src.core.crs_manager import ensure_metric_crs, reproject_geometry
from src.schemas import AnomalyFeature, AnomalyTypeLiteral

# Factor mínimo de área expresado en píxeles del raster: un contorno medible necesita al
# menos este número de píxeles; por debajo, cualquier "detección" es un artefacto de
# interpolación del DEM y debe filtrarse sin importar el `min_area` solicitado por zona.
MIN_AREA_PIXEL_FACTOR: float = 2.0


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

    # 2a. Círculo a resolución gruesa: circularidad muy alta (>= 1.05) es inequívoca de un
    #     contorno circular y domina sobre la rectangularidad, que en blobs de pocos píxeles
    #     queda inflada por la corrección de medio píxel (un cuadrado rasterizado no supera ~1.0).
    if circularity >= 1.05 and aspect_ratio <= 1.5:
        conf = min(0.98, 0.60 + 0.38 * min(circularity, 1.2))
        return "estructura_circular", round(float(conf), 3)

    # 2. Estructura circular (chenque, corral circular, torreón): alta circularidad y baja elongación
    if circularity >= 0.76 and aspect_ratio <= 1.45 and rectangularity < 0.86:
        conf = min(0.98, 0.60 + 0.38 * circularity)
        return "estructura_circular", round(float(conf), 3)

    # 3. Recinto ortogonal (pirca cuadrangular/rectangular, cancha, kallanka): alta rectangularidad.
    # El atajo por vértices exige además circularidad <= 0.85: un cuadrado rasterizado tiene
    # circularidad ~0.785, mientras que un círculo a resolución gruesa se aproxima con 4-6
    # vértices y circularidad > 0.9, y no debe clasificarse como recinto ortogonal.
    if rectangularity >= 0.80 or (4 <= num_vertices <= 6 and rectangularity >= 0.72 and circularity <= 0.85):
        conf = min(0.98, 0.55 + 0.43 * rectangularity)
        return "recinto_ortogonal", round(float(conf), 3)

    # Fallback basado en el descriptor dominante (tolerancia epsilon en el límite de aspect 1.5)
    if circularity > rectangularity and aspect_ratio <= 1.5 + 1e-6:
        conf = max(0.50, min(0.90, 0.50 + 0.35 * circularity))
        return "estructura_circular", round(float(conf), 3)

    conf = max(0.50, min(0.90, 0.50 + 0.35 * rectangularity))
    return "recinto_ortogonal", round(float(conf), 3)


def _classify_negative_morphology(
    rectangularity: float,
    circularity: float,
    aspect_ratio: float,
) -> Tuple[AnomalyTypeLiteral, float]:
    """Clasifica contornos de relieve negativo (hundimientos) según sus descriptores geométricos.

    Args:
        rectangularity: Relación área / caja mínima rotada [0-1].
        circularity: Índice isoperimétrico `4 * pi * A / P^2` [0-1].
        aspect_ratio: Relación largo/ancho de la caja mínima rotada (>= 1.0).

    Returns:
        Tupla `(anomaly_type, confidence)` con `zanja_lineal` o `estructura_hundida`.
    """
    # Zanja o canal lineal: alta elongación
    if aspect_ratio >= 3.5:
        conf = min(0.95, 0.60 + 0.05 * min(aspect_ratio - 3.5, 5.0))
        return "zanja_lineal", round(float(conf), 3)

    # Pozo, casa-pozo, patio hundido o túmulo deprimido: descriptores dominantes
    dominant = max(circularity, rectangularity)
    conf = max(0.50, min(0.92, 0.52 + 0.40 * dominant))
    return "estructura_hundida", round(float(conf), 3)


def _build_sign_pass_mask(
    slrm: np.ndarray,
    slope: np.ndarray,
    valid_mask: np.ndarray,
    min_dz: float,
    max_slope_deg: float,
    sign: int,
) -> np.ndarray:
    """Construye la máscara binaria OpenCV para un pase de signo (+1 positivo, -1 negativo).

    Espeja el SLRM (`slrm * sign`) de modo que las anomalías del signo buscado queden como
    elevaciones positivas, y aplica la cadena filtro bilateral -> umbral adaptativo ->
    máscara de microelevación -> máscara de pendiente -> clausura morfológica.
    """
    signed = slrm * sign
    signed_clean = np.where(valid_mask, np.clip(signed, 0.0, 3.0), 0.0).astype(np.float32)
    signed_u8 = np.clip((signed_clean / 3.0) * 255.0, 0, 255).astype(np.uint8)

    # Filtro bilateral sobre imagen uint8 (preserva bordes de pircas y montículos)
    filtered_u8 = cv2.bilateralFilter(signed_u8, d=7, sigmaColor=35, sigmaSpace=35)
    filtered_signed = (filtered_u8.astype(np.float32) / 255.0) * 3.0

    # Umbral adaptativo sobre la imagen filtrada + condición estricta de microelevación [min_dz, 3.0m]
    adaptive_bin = cv2.adaptiveThreshold(
        filtered_u8,
        maxValue=255,
        adaptiveMethod=cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        thresholdType=cv2.THRESH_BINARY,
        blockSize=31,
        C=-2,
    )

    elevation_mask = (
        (filtered_signed >= min_dz)
        & (filtered_signed <= 3.0)
        & (signed >= min_dz)
        & (signed <= 3.0)
    )
    slope_mask = slope <= max_slope_deg
    combined_mask = np.where(
        valid_mask & elevation_mask & slope_mask & (adaptive_bin > 0),
        255,
        0,
    ).astype(np.uint8)

    # Clausura morfológica suave para consolidar bordes contiguos sin distorsionar el área
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    return cv2.morphologyEx(combined_mask, cv2.MORPH_CLOSE, kernel, iterations=1)


def _extract_candidates_from_mask(
    closed_mask: np.ndarray,
    slrm: np.ndarray,
    valid_mask: np.ndarray,
    transform: rasterio.Affine,
    crs_str: str,
    pixel_area_m2: float,
    min_area: float,
    max_area: float,
    sign: int,
    start_idx: int,
    border_margin_px: int = 0,
) -> List[Dict[str, Any]]:
    """Extrae y clasifica contornos de una máscara binaria para un pase de signo.

    Args:
        sign: +1 para relieve positivo, -1 para relieve negativo.
        start_idx: Índice global inicial para numerar los candidatos sin colisiones entre pases.
        border_margin_px: Margen de borde en píxeles; contornos que lo tocan se descartan porque
            la tendencia SLRM está sesgada cerca del borde del raster (modo 'nearest' del
            filtro gaussiano) y la cobertura real la garantiza el overlap del tiling.

    Returns:
        Lista de candidatos en crudo con geometría métrica y WGS84, tipología y confianza.
    """
    contours, _ = cv2.findContours(closed_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)

    raw_candidates: List[Dict[str, Any]] = []
    res_x = float(abs(transform.a))
    res_y = float(abs(transform.e))

    # Margen de borde: los hundimientos siempre exigen depresión cerrada (>= 2 px de margen
    # propio: un pozo queda contenido en la celda, mientras que una vaguada o cauce natural
    # que atraviesa el tile toca el borde y se descarta). Para el pase positivo, el margen
    # solo se aplica cuando el llamador lo solicita (tiles chicos en píxeles).
    border_pad_px = max(border_margin_px, 2) if sign < 0 else border_margin_px
    img_h, img_w = closed_mask.shape

    for offset, cnt in enumerate(contours, start=0):
        idx = start_idx + offset
        if border_pad_px > 0:
            cnt_xs = cnt[:, 0, 0]
            cnt_ys = cnt[:, 0, 1]
            touches_border = (
                cnt_xs.min() <= border_pad_px
                or cnt_ys.min() <= border_pad_px
                or cnt_xs.max() >= (img_w - 1 - border_pad_px)
                or cnt_ys.max() >= (img_h - 1 - border_pad_px)
            )
            if touches_border:
                continue

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

        if sign > 0:
            anomaly_type, confidence = _classify_contour_morphology(
                rectangularity=rectangularity,
                circularity=circularity,
                aspect_ratio=aspect_ratio,
                num_vertices=num_vertices,
            )
        else:
            anomaly_type, confidence = _classify_negative_morphology(
                rectangularity=rectangularity,
                circularity=circularity,
                aspect_ratio=aspect_ratio,
            )

        # Desviación media real (con signo) dentro del contorno respecto a la tendencia local
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
                "relief_sign": "positivo" if sign > 0 else "negativo",
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

    return raw_candidates


def detect_anomalies(
    slrm_path: Union[str, Path],
    slope_path: Union[str, Path],
    min_area: float = 12.0,
    max_area: float = 6000.0,
    min_dz: float = 0.15,
    max_slope_deg: float = 35.0,
    border_margin_px: int = 0,
) -> Dict[str, Any]:
    """Detecta estructuras arqueológicas en modelos SLRM y Slope usando OpenCV y clustering espacial.

    Pasos del algoritmo:
    1. Verifica que `slrm_path` y `slope_path` estén en proyección métrica POSGAR 2007 y reemplaza
       valores `nodata` con `np.nan`.
    2. Aplica un piso físico de área: ningún contorno por debajo de `MIN_AREA_PIXEL_FACTOR` píxeles
       puede provenir de una estructura real a la resolución nativa del DEM.
    3. Ejecuta dos pases de detección: relieve positivo (recintos, círculos, terrazas) y relieve
       negativo (pozos, casas-pozo, zanjas), con la cadena bilateral + umbral adaptativo + clausura.
       Los hundimientos deben ser depresiones cerradas dentro de la celda: contornos que tocan el
       borde del tile (vaguadas, cauces que lo atraviesan) se descartan como morfología natural.
    4. Clasifica cada estructura según su tipología morfológica y su signo de relieve.
    5. Ejecuta clustering espacial con `scipy.spatial.cKDTree` para identificar complejos
       arquitectónicos (estructuras a menos de 80 m entre sí).
    6. Reproyecta los polígonos y centroides a `EPSG:4326` (WGS84) y retorna un GeoJSON `FeatureCollection`.

    Args:
        slrm_path: Ruta al GeoTIFF del Simple Local Relief Model.
        slope_path: Ruta al GeoTIFF de pendiente en grados.
        min_area: Área mínima solicitada en metros cuadrados (se eleva al piso físico por resolución).
        max_area: Área máxima en metros cuadrados para considerar una anomalía.
        min_dz: Desviación local mínima absoluta en metros (aplica a positivo y negativo).
        max_slope_deg: Pendiente máxima en grados para aceptar un contorno.
        border_margin_px: Margen de borde en píxeles para descartar contornos que lo tocan
            (la tendencia SLRM está sesgada cerca del borde; la cobertura real la da el overlap).

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

    # Piso físico de área coherente con la resolución nativa del raster: un contorno menor a
    # `MIN_AREA_PIXEL_FACTOR` píxeles es indistinguible del ruido de interpolación del DEM.
    min_area_requested = float(min_area)
    min_area_effective = max(min_area_requested, pixel_area_m2 * MIN_AREA_PIXEL_FACTOR)
    floor_applied = min_area_effective > min_area_requested

    raw_candidates: List[Dict[str, Any]] = []
    next_idx = 1
    for sign in (1, -1):
        closed_mask = _build_sign_pass_mask(
            slrm=slrm,
            slope=slope,
            valid_mask=valid_mask,
            min_dz=min_dz,
            max_slope_deg=max_slope_deg,
            sign=sign,
        )
        pass_candidates = _extract_candidates_from_mask(
            closed_mask=closed_mask,
            slrm=slrm,
            valid_mask=valid_mask,
            transform=transform,
            crs_str=crs_str,
            pixel_area_m2=pixel_area_m2,
            min_area=min_area_effective,
            max_area=max_area,
            sign=sign,
            start_idx=next_idx,
            border_margin_px=border_margin_px,
        )
        next_idx += len(pass_candidates) + 1
        raw_candidates.extend(pass_candidates)

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

        # Evidencia observable estructurada (Etapa 1.3: separar saliencia geométrica de probabilidad arqueológica)
        observable_evidence: Dict[str, Any] = {
            "geometry_descriptors": {
                "rectangularity": round(float(cand["rectangularity"]), 3),
                "circularity": round(float(cand["circularity"]), 3),
                "aspect_ratio": round(float(cand["aspect_ratio"]), 3),
            },
            "dimensions_m2": round(float(cand["area_m2"]), 2),
            "relative_relief_m": round(float(cand["mean_elevation_m"]), 3),
            "relief_sign": "positive" if cand["relief_sign"] == "positivo" else "negative",
            "min_area_effective_m2": round(float(min_area_effective), 2),
            "physical_floor_applied": bool(min_area_effective > min_area),
            "pixel_area_m2": round(float(pixel_area_m2), 4),
            "score_interpretation": "geometric_topographic_salience_not_archaeological_probability",
        }

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
            anomaly_family="POTENTIAL_ANTHROPOGENIC",
            lifecycle_state="ALGORITHMIC_DETECTION",
            observable_evidence=observable_evidence,
        )

        feature_dict: Dict[str, Any] = {
            "type": "Feature",
            "id": validated_feat.id,
            "geometry": validated_feat.geometry_geojson,
            "properties": {
                "id": validated_feat.id,
                "anomaly_type": validated_feat.anomaly_type,
                "anomaly_family": validated_feat.anomaly_family,
                "lifecycle_state": validated_feat.lifecycle_state,
                "relief_sign": cand["relief_sign"],
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
                "observable_evidence": validated_feat.observable_evidence,
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
            "pixel_area_m2": round(pixel_area_m2, 4),
            "min_area_requested_m2": round(min_area_requested, 2),
            "min_area_effective_m2": round(min_area_effective, 2),
            "min_area_floor_applied": floor_applied,
        },
        "features": features,
    }
