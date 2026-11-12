"""Validación cruzada espacial con WFS del IGN Argentina, Overpass API (OSM) y GeoPackage local."""

import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import geopandas as gpd
import httpx
import numpy as np
import shapely
from pyproj import CRS, Transformer
from shapely.geometry import Point, shape

from src.config import settings
from src.core.crs_manager import get_posgar_faja
from src.schemas import ClassificationLiteral, ValidationResult


async def _query_ign_wfs(
    lat: float,
    lon: float,
    client: httpx.AsyncClient,
    delta_deg: float = 0.005,
) -> tuple[List[Dict[str, Any]], Optional[float]]:
    """Consulta el servicio WFS del IGN para infraestructura y cursos de agua (`ign:linea_de_agua`).

    Calcula la distancia métrica exacta al curso de agua más cercano reproyectando a la faja POSGAR 2007.
    Si no se encuentra ningún curso de agua o la consulta falla, retorna None.
    """
    min_lon, max_lon = lon - delta_deg, lon + delta_deg
    min_lat, max_lat = lat - delta_deg, lat + delta_deg
    bbox_str = f"{min_lat},{min_lon},{max_lat},{max_lon},EPSG:4326"

    ign_matches: List[Dict[str, Any]] = []
    min_water_dist_m: Optional[float] = None

    target_epsg = get_posgar_faja(lon)
    to_posgar = Transformer.from_crs(CRS.from_epsg(4326), CRS.from_epsg(target_epsg), always_xy=True)
    candidate_pt_posgar = Point(*to_posgar.transform(lon, lat))

    layers = ["ign:linea_de_agua", "ign:puntos_de_asentamientos_y_edificios"]
    for layer_name in layers:
        params = {
            "service": "WFS",
            "version": "1.0.0",
            "request": "GetFeature",
            "typeName": layer_name,
            "bbox": f"{min_lon},{min_lat},{max_lon},{max_lat}",
            "outputFormat": "application/json",
            "maxFeatures": "50",
        }
        try:
            resp = await client.get(settings.ign_wfs_url, params=params)
            resp.raise_for_status()
            payload = resp.json()
            features = payload.get("features", [])
            for feat in features:
                props = feat.get("properties", {}) or {}
                geom_dict = feat.get("geometry")
                dist_m: Optional[float] = None
                if geom_dict:
                    geom_wgs = shape(geom_dict)
                    geom_posgar = shapely.transform(
                        geom_wgs,
                        lambda coords: np.column_stack(to_posgar.transform(coords[:, 0], coords[:, 1])),
                    )
                    dist_m = float(candidate_pt_posgar.distance(geom_posgar))
                    if layer_name == "ign:linea_de_agua":
                        if min_water_dist_m is None or dist_m < min_water_dist_m:
                            min_water_dist_m = round(dist_m, 2)

                ign_matches.append(
                    {
                        "layer": layer_name,
                        "id": feat.get("id", ""),
                        "properties": props,
                        "distance_m": round(dist_m, 2) if dist_m is not None else None,
                        "bbox_queried": bbox_str,
                    }
                )
        except Exception:
            # Tolerancia a fallos de red o capas no disponibles sin interrumpir la validación
            continue

    return ign_matches, min_water_dist_m


async def _query_overpass_osm(
    lat: float,
    lon: float,
    client: httpx.AsyncClient,
    radius_m: int = 150,
) -> List[Dict[str, Any]]:
    """Consulta Overpass API en un radio de 150 m buscando `historic=*`, `barrier=wall|fence`, `building=*`."""
    overpass_ql = f"""
    [out:json][timeout:20];
    (
      node["historic"](around:{radius_m},{lat},{lon});
      way["historic"](around:{radius_m},{lat},{lon});
      relation["historic"](around:{radius_m},{lat},{lon});
      way["barrier"~"^(wall|fence)$"](around:{radius_m},{lat},{lon});
      way["building"](around:{radius_m},{lat},{lon});
      node["building"](around:{radius_m},{lat},{lon});
    );
    out body center;
    """
    osm_matches: List[Dict[str, Any]] = []
    try:
        resp = await client.post(settings.overpass_url, data={"data": overpass_ql.strip()})
        resp.raise_for_status()
        payload = resp.json()
        for elem in payload.get("elements", []):
            tags = elem.get("tags", {}) or {}
            osm_matches.append(
                {
                    "osm_id": elem.get("id"),
                    "osm_type": elem.get("type"),
                    "tags": tags,
                }
            )
    except Exception:
        pass
    return osm_matches


def _check_local_gpkg(
    lat: float,
    lon: float,
    known_gpkg_path: Optional[Union[str, Path]],
    buffer_m: float = 200.0,
) -> List[Dict[str, Any]]:
    """Consulta una capa GeoPackage local de sitios arqueológicos registrados en POSGAR 2007."""
    if not known_gpkg_path:
        return []
    gpkg_file = Path(known_gpkg_path)
    if not gpkg_file.exists():
        return []

    try:
        gdf = gpd.read_file(gpkg_file)
        if gdf.empty:
            return []
        target_epsg = get_posgar_faja(lon)
        if gdf.crs is None:
            gdf = gdf.set_crs(epsg=4326)
        gdf_metric = gdf.to_crs(epsg=target_epsg)

        to_posgar = Transformer.from_crs(CRS.from_epsg(4326), CRS.from_epsg(target_epsg), always_xy=True)
        pt_metric = Point(*to_posgar.transform(lon, lat))

        distances = gdf_metric.geometry.distance(pt_metric)
        nearby = gdf_metric[distances <= buffer_m]
        matches: List[Dict[str, Any]] = []
        for idx, row in nearby.iterrows():
            props = {k: v for k, v in row.items() if k != "geometry"}
            props["distance_m"] = round(float(distances.loc[idx]), 2)
            matches.append(props)
        return matches
    except Exception:
        return []


def _classify_validation_outcome(
    ign_matches: List[Dict[str, Any]],
    osm_matches: List[Dict[str, Any]],
    gpkg_matches: List[Dict[str, Any]],
) -> ClassificationLiteral:
    """Determina la clasificación final según las coincidencias en IGN, OSM y GPKG local."""
    # 1. Si coincide con un sitio en el GeoPackage local o tiene etiqueta historic=archaeological_site / ruins en OSM
    if gpkg_matches:
        return "SITIO_REGISTRADO"

    for osm in osm_matches:
        tags = osm.get("tags", {})
        historic_val = str(tags.get("historic", "")).lower()
        if historic_val in {"archaeological_site", "ruins", "monument", "fort", "castle", "tomb"}:
            return "SITIO_REGISTRADO"

    # 2. Si coincide con edificios modernos, galpones o alambrados/muros modernos en OSM o asentamientos actuales en IGN
    for osm in osm_matches:
        tags = osm.get("tags", {})
        if "building" in tags or tags.get("barrier") in {"fence", "wall"} or "landuse" in tags:
            return "FALSO_POSITIVO_MODERNO"

    for ign in ign_matches:
        if ign.get("layer") != "ign:linea_de_agua":
            dist = ign.get("distance_m")
            if dist is None or dist <= 150.0:
                return "FALSO_POSITIVO_MODERNO"

    # 3. Sin infraestructura moderna ni registro previo -> Candidato inédito
    return "CANDIDATO_INEDITO"


async def validate_anomaly_async(
    lat: float,
    lon: float,
    known_gpkg_path: Optional[Union[str, Path]] = None,
    anomaly_id: str = "ARQ-0001",
    http_client: Optional[httpx.AsyncClient] = None,
) -> ValidationResult:
    """Ejecuta de forma asíncrona la validación espacial cruzada (IGN WFS + Overpass OSM + GPKG local)."""
    close_client = False
    if http_client is None:
        http_client = httpx.AsyncClient(timeout=settings.http_timeout_seconds)
        close_client = True

    try:
        (ign_matches, water_dist_m), osm_matches = await asyncio.gather(
            _query_ign_wfs(lat=lat, lon=lon, client=http_client),
            _query_overpass_osm(lat=lat, lon=lon, client=http_client),
        )
    finally:
        if close_client:
            await http_client.aclose()

    gpkg_path_to_use = known_gpkg_path or settings.known_sites_gpkg_path
    gpkg_matches = _check_local_gpkg(lat=lat, lon=lon, known_gpkg_path=gpkg_path_to_use)

    classification = _classify_validation_outcome(
        ign_matches=ign_matches,
        osm_matches=osm_matches,
        gpkg_matches=gpkg_matches,
    )

    combined_ign = ign_matches + [{"layer": "local_gpkg", "properties": m} for m in gpkg_matches]

    return ValidationResult(
        anomaly_id=anomaly_id,
        classification=classification,
        ign_matches=combined_ign,
        osm_matches=osm_matches,
        literature_matches=[],
        distance_to_water_m=water_dist_m,
    )


def validate_anomaly(
    lat: float,
    lon: float,
    known_gpkg_path: Optional[Union[str, Path]] = None,
    anomaly_id: str = "ARQ-0001",
) -> ValidationResult:
    """Envoltorio síncrono/compatible con bucle de eventos para validar un candidato arqueológico.

    Args:
        lat: Latitud geográfica en grados decimales (WGS84).
        lon: Longitud geográfica en grados decimales (WGS84).
        known_gpkg_path: Ruta opcional al archivo GeoPackage de sitios arqueológicos registrados.
        anomaly_id: Identificador único del candidato (por defecto 'ARQ-0001').

    Returns:
        Instancia validada de `ValidationResult`.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                asyncio.run,
                validate_anomaly_async(
                    lat=lat,
                    lon=lon,
                    known_gpkg_path=known_gpkg_path,
                    anomaly_id=anomaly_id,
                ),
            )
            return future.result()

    return asyncio.run(
        validate_anomaly_async(
            lat=lat,
            lon=lon,
            known_gpkg_path=known_gpkg_path,
            anomaly_id=anomaly_id,
        )
    )
