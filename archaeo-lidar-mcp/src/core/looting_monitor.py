"""Vigilancia patrimonial: detección de patrones compatibles con saqueo (*huaqueo*).

Regla pericial: una depresión cerrada circular de 5 a 25 m de diámetro con `dZ` negativo
neto y reborde periférico, emplazada a menos de 1000 m de un sitio arqueológico registrado
(catálogo local), con etiqueta `historic=*` en OSM o infraestructura/asentamiento en el IGN,
se marca con prioridad patrimonial `ALERTA_SAQUEO`. El candidato se propaga al prompt del
Juez Pericial VLM y a una sección dedicada del Dossier INAPL (Ley 25.743).

Referencia metodológica: detección satelital de saqueo (Parcak 2015; Parcak et al. 2016),
trasladada aquí a microtopografía LiDAR/DEM.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
from pyproj import CRS, Transformer

from src.config import settings

# Diámetro esperado de un pozo de huaquero (m) y radio de alerta alrededor de sitios conocidos
MIN_DIAMETER_M: float = 5.0
MAX_DIAMETER_M: float = 25.0
ALERT_RADIUS_M: float = 1000.0


def _nearby_known_sites(
    lat: float,
    lon: float,
    known_gpkg_path: Optional[Union[str, Path]] = None,
    buffer_m: float = ALERT_RADIUS_M,
) -> List[Dict[str, Any]]:
    """Sitios arqueológicos registrados del catálogo local a menos de `buffer_m` del candidato."""
    import geopandas as gpd
    from shapely.geometry import Point

    gpkg_path = Path(known_gpkg_path) if known_gpkg_path else settings.known_sites_gpkg_path
    if not gpkg_path.exists():
        return []
    try:
        gdf = gpd.read_file(gpkg_path)
        if gdf.empty:
            return []
        from src.core.crs_manager import get_posgar_faja
        target_epsg = get_posgar_faja(lon)
        gdf_metric = gdf.to_crs(epsg=target_epsg)
        to_metric = Transformer.from_crs(CRS.from_epsg(4326), CRS.from_epsg(target_epsg), always_xy=True)
        pt = Point(*to_metric.transform(lon, lat))
        distances = gdf_metric.geometry.distance(pt)
        nearby = gdf_metric[distances <= buffer_m]
        matches: List[Dict[str, Any]] = []
        for idx, row in nearby.iterrows():
            props = {k: v for k, v in row.items() if k != "geometry"}
            props["distance_m"] = round(float(distances.loc[idx]), 1)
            matches.append(props)
        matches.sort(key=lambda m: m["distance_m"])
        return matches
    except Exception:
        return []


def evaluate_looting_alert(
    props: Dict[str, Any],
    known_gpkg_path: Optional[Union[str, Path]] = None,
    osm_matches: Optional[List[Dict[str, Any]]] = None,
    ign_matches: Optional[List[Dict[str, Any]]] = None,
) -> Optional[Dict[str, Any]]:
    """Determina si un candidato constituye una `ALERTA_SAQUEO`.

    Condiciones (todas obligatorias):
    1. Relieve negativo (`estructura_hundida`, o `relief_sign == "negativo"`).
    2. Forma circular/elongación baja (`circularity >= 0.5` y `aspect_ratio <= 1.6`):
       los pozos de huaquero son circulares; las zanjas naturales no.
    3. Diámetro equivalente en [5, 25] m.
    4. dZ negativo neto.
    5. Proximidad (< 1000 m) a un sitio registrado del catálogo, o contexto
       patrimonial (`historic=*` en OSM) o asentamiento/infraestructura IGN cercana.

    Returns:
        Dict con `alert="ALERTA_SAQUEO"`, sitio más cercano y evidencia, o None.
    """
    anomaly_type = str(props.get("anomaly_type", ""))
    relief_sign = props.get("relief_sign")
    is_negative = anomaly_type == "estructura_hundida" or relief_sign == "negativo"
    if not is_negative:
        return None

    circularity = float(props.get("circularity", 0.0) or 0.0)
    aspect_ratio = float(props.get("aspect_ratio", 0.0) or 0.0)
    if anomaly_type == "zanja_lineal" or aspect_ratio > 1.6 or circularity < 0.5:
        return None  # zanjas/canales lineales: no perfil de huaquero

    area_m2 = float(props.get("area_m2", 0.0) or 0.0)
    diameter_m = 2.0 * math_sqrt(area_m2 / np.pi)
    if diameter_m < MIN_DIAMETER_M or diameter_m > MAX_DIAMETER_M:
        return None

    if float(props.get("mean_elevation_m", 0.0) or 0.0) >= 0.0:
        return None

    # Contexto patrimonial: catálogo local, OSM historic=* o IGN cercano
    nearest_site: Optional[Dict[str, Any]] = None
    centroid = props.get("centroid_wgs84")
    if centroid and len(centroid) == 2:
        sites = _nearby_known_sites(lat=float(centroid[1]), lon=float(centroid[0]), known_gpkg_path=known_gpkg_path)
        if sites:
            nearest_site = sites[0]

    osm_matches = osm_matches or []
    has_historic_context = any(
        str((m.get("tags") or {}).get("historic", "")).lower()
        in {"archaeological_site", "ruins", "monument", "fort", "castle", "tomb"}
        for m in osm_matches
    )
    ign_matches = ign_matches or []
    has_ign_context = any(
        (m.get("layer") or "") != "ign:linea_de_agua" and m.get("distance_m") is not None and float(m["distance_m"]) <= ALERT_RADIUS_M
        for m in ign_matches
    )

    if nearest_site is None and not (has_historic_context or has_ign_context):
        return None

    alert: Dict[str, Any] = {
        "alert": "ALERTA_SAQUEO",
        "diameter_m": round(diameter_m, 2),
        "nearest_known_site": (
            {k: nearest_site.get(k) for k in ("name", "site_type", "era", "distance_m")}
            if nearest_site else None
        ),
        "osm_historic_context": has_historic_context,
        "ign_settlement_context": has_ign_context,
        "legal_note": (
            "Depresión cerrada compatible con pozo de huaquero en el entorno de un sitio "
            "registrado. Comunicar de inmediato a la Delegación regional del INAPL y a la "
            "dirección provincial de patrimonio (Ley Nacional N° 25.743, art. 20 y 23)."
        ),
    }
    return alert


def math_sqrt(value: float) -> float:
    """Raíz cuadrada (helper explícito para evitar dependencias dispersas)."""
    import math
    return math.sqrt(max(0.0, value))
