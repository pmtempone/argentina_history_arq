"""Router de proveedores DEM multi-fuente con lectura por ventana HTTP Range Request (COG/STAC/WCS).

Reglas de diseño:
1. PROHIBIDO descargar escenas completas antes de recortar: toda lectura remota sobre COG o
   GeoTIFF usa `rasterio.open(url)` + `rasterio.windows.from_bounds(bbox_wgs84)`.
2. Honestidad de resolución nativa:
   - Copernicus GLO-30, FABDEM V1-2 y ALOS AW3D30 tienen resolución topográfica nativa de `30.0 m`.
   - Los DEM incluidos en paquetes ALOS PALSAR RTC (12,5 m) fuera de EE. UU. son SRTM de 30 m
     remuestreado a 12,5 m; por lo tanto nunca se reporta 12,5 m como resolución DEM nativa.
     El dato de 12,5 m de ALOS PALSAR se reserva exclusivamente para retrodispersión SAR Banda L.
   - Solo vuelos aerofotogramétricos IGN MDE-Ar (`ign_wcs`) reportan `5.0 m` nativos (o UAV < 1 m).
"""

import logging
import math
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx
import numpy as np
import rasterio
from rasterio.windows import from_bounds

from src.config import settings

logger = logging.getLogger(__name__)

# Asegurar variables GDAL/VSICURL para lecturas remotas por bloques sin listar directorios
os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
os.environ.setdefault("CPL_VSIL_CURL_ALLOWED_EXTENSIONS", ".tif,.tiff,.jp2")
os.environ.setdefault("VSI_CACHE", "TRUE")
os.environ.setdefault("VSI_CACHE_SIZE", "25000000")

COPERNICUS_AWS_BASE_URL = "https://copernicus-dem-30m.s3.amazonaws.com"


def build_copernicus_cog_url(lat: float, lon: float) -> str:
    """Construye la URL HTTPS pública del Cloud Optimized GeoTIFF (COG) en AWS Open Data."""
    lat_floor = int(math.floor(lat))
    lon_floor = int(math.floor(lon))
    ns = "S" if lat_floor < 0 else "N"
    ew = "W" if lon_floor < 0 else "E"
    tile_id = f"Copernicus_DSM_COG_10_{ns}{abs(lat_floor):02d}_00_{ew}{abs(lon_floor):03d}_00_DEM"
    return f"{COPERNICUS_AWS_BASE_URL}/{tile_id}/{tile_id}.tif"


def _write_window_geotiff(
    src_url_or_path: str,
    bbox_wgs84: Tuple[float, float, float, float],
    out_path: Path,
    provider_tag: str,
    native_res_m: float,
) -> Path:
    """Abre un raster remoto/local y transfiere únicamente la ventana del bbox_wgs84."""
    min_lon, min_lat, max_lon, max_lat = bbox_wgs84
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with rasterio.open(src_url_or_path) as src:
        window = from_bounds(min_lon, min_lat, max_lon, max_lat, transform=src.transform)
        window = window.round_offsets().round_lengths()
        if window.width < 2 or window.height < 2:
            raise ValueError(f"Ventana DEM demasiado pequeña ({window.width}x{window.height}) en {src_url_or_path}")

        data = src.read(1, window=window, boundless=True, fill_value=-9999.0).astype(np.float32)
        if src.nodata is not None:
            data[np.isclose(data, float(src.nodata))] = -9999.0
        if np.all((data <= -9000.0) | np.isnan(data)):
            raise ValueError(f"Ventana DEM sin datos válidos en {src_url_or_path}")

        win_transform = rasterio.windows.transform(window, src.transform)
        profile = src.profile.copy()
        profile.update(
            {
                "driver": "GTiff",
                "height": int(data.shape[0]),
                "width": int(data.shape[1]),
                "count": 1,
                "dtype": "float32",
                "transform": win_transform,
                "crs": src.crs or "EPSG:4326",
                "nodata": -9999.0,
                "compress": "deflate",
            }
        )
        # Limpiar tiling heredado si la ventana es más chica que el bloque original
        profile.pop("blockxsize", None)
        profile.pop("blockysize", None)
        profile.pop("tiled", None)

        with rasterio.open(out_path, "w", **profile) as dst:
            dst.write(data, 1)
            dst.update_tags(
                DEM_PROVIDER=provider_tag,
                NATIVE_RESOLUTION_M=str(native_res_m),
            )

    return out_path


def _fetch_copernicus_aws(
    bbox_wgs84: Tuple[float, float, float, float],
    out_path: Path,
    zone_meta: Dict[str, Any],
) -> Dict[str, Any]:
    min_lon, min_lat, max_lon, max_lat = bbox_wgs84
    center_lon = (min_lon + max_lon) / 2.0
    center_lat = (min_lat + max_lat) / 2.0
    tile_id = zone_meta.get("copernicus_tile")
    cog_url = (
        f"{COPERNICUS_AWS_BASE_URL}/{tile_id}/{tile_id}.tif"
        if tile_id
        else build_copernicus_cog_url(center_lat, center_lon)
    )
    _write_window_geotiff(cog_url, bbox_wgs84, out_path, "copernicus_aws", 30.0)
    return {
        "path": out_path,
        "provider_used": "copernicus_aws",
        "native_resolution_m": 30.0,
        "is_synthetic_fallback": False,
    }


def _fetch_planetary_stac(
    bbox_wgs84: Tuple[float, float, float, float],
    out_path: Path,
    collection: str = "cop-dem-glo-30",
    provider_label: str = "planetary_stac",
) -> Dict[str, Any]:
    """Consulta Planetary Computer STAC y extrae únicamente el recorte bbox_wgs84 vía VSICURL."""
    import planetary_computer
    from pystac_client import Client

    catalog = Client.open(settings.planetary_stac_url, modifier=planetary_computer.sign_inplace)
    search = catalog.search(collections=[collection], bbox=list(bbox_wgs84), max_items=4)
    items = list(search.items())
    if not items:
        raise RuntimeError(f"Sin items STAC en '{collection}' para bbox {bbox_wgs84}")

    item = items[0]
    asset = item.assets.get("data") or next(iter(item.assets.values()))
    _write_window_geotiff(asset.href, bbox_wgs84, out_path, provider_label, 30.0)
    return {
        "path": out_path,
        "provider_used": provider_label,
        "native_resolution_m": 30.0,
        "is_synthetic_fallback": False,
    }


def _fetch_fabdem(
    bbox_wgs84: Tuple[float, float, float, float],
    out_path: Path,
) -> Dict[str, Any]:
    """Obtiene FABDEM V1-2 (DTM 30 m sin cobertura arbórea) vía GEE o repositorio local."""
    # 1. Revisar tiles FABDEM locales en data/raw/fabdem/
    local_fabdem_dir = settings.data_dir / "fabdem"
    if local_fabdem_dir.exists():
        min_lon, min_lat, max_lon, max_lat = bbox_wgs84
        for tif_path in sorted(local_fabdem_dir.glob("*.tif")):
            try:
                with rasterio.open(tif_path) as src:
                    b = src.bounds
                    if b.left <= max_lon and b.right >= min_lon and b.bottom <= max_lat and b.top >= min_lat:
                        _write_window_geotiff(str(tif_path), bbox_wgs84, out_path, "fabdem_local", 30.0)
                        return {
                            "path": out_path,
                            "provider_used": "fabdem",
                            "native_resolution_m": 30.0,
                            "is_synthetic_fallback": False,
                        }
            except Exception:
                continue

    # 2. Google Earth Engine si GEE_PROJECT_ID está configurado y earthengine-api disponible
    if settings.gee_project_id:
        try:
            import ee  # type: ignore[import-not-found]

            ee.Initialize(project=settings.gee_project_id)
            min_lon, min_lat, max_lon, max_lat = bbox_wgs84
            region = ee.Geometry.Rectangle([min_lon, min_lat, max_lon, max_lat])
            col = ee.ImageCollection(settings.fabdem_stac_or_gee_collection).filterBounds(region)
            img = col.mosaic().clip(region)
            url = img.getDownloadURL(
                {
                    "scale": 30,
                    "region": region,
                    "format": "GEO_TIFF",
                    "crs": "EPSG:4326",
                }
            )
            with httpx.Client(timeout=settings.http_timeout_seconds) as client:
                resp = client.get(url)
                resp.raise_for_status()
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_bytes(resp.content)
            return {
                "path": out_path,
                "provider_used": "fabdem",
                "native_resolution_m": 30.0,
                "is_synthetic_fallback": False,
            }
        except Exception as exc:
            logger.info("FABDEM vía GEE no disponible (%s); continuando con fallback.", exc)
            raise

    logger.info("FABDEM requiere GEE_PROJECT_ID o tile local en data/raw/fabdem/; aplicando fallback.")
    raise RuntimeError("FABDEM no configurado (sin GEE_PROJECT_ID ni tile local).")


def _fetch_ign_wcs(
    bbox_wgs84: Tuple[float, float, float, float],
    out_path: Path,
) -> Dict[str, Any]:
    """Consulta cobertura MDT de alta resolución (5 m) vía WCS del IGN Argentina."""
    min_lon, min_lat, max_lon, max_lat = bbox_wgs84
    params = {
        "service": "WCS",
        "version": "1.0.0",
        "request": "GetCoverage",
        "coverage": "ign:mde_ar_5m",
        "bbox": f"{min_lon},{min_lat},{max_lon},{max_lat}",
        "crs": "EPSG:4326",
        "format": "GeoTIFF",
        "resx": "0.00005",
        "resy": "0.00005",
    }
    with httpx.Client(timeout=min(10.0, settings.http_timeout_seconds)) as client:
        resp = client.get(settings.ign_wfs_url, params=params)
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "").lower()
        if "tiff" not in content_type and not resp.content[:4] in (b"II*\x00", b"MM\x00*"):
            raise RuntimeError("IGN WCS no devolvió un GeoTIFF válido para este polígono.")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(resp.content)

    # Verificar que el raster tenga datos válidos
    with rasterio.open(out_path) as src:
        arr = src.read(1)
        if np.all(np.isnan(arr)) or np.all(arr <= -9000.0):
            out_path.unlink(missing_ok=True)
            raise RuntimeError("IGN WCS devolvió cobertura vacía para este polígono.")

    return {
        "path": out_path,
        "provider_used": "ign_wcs",
        "native_resolution_m": 5.0,
        "is_synthetic_fallback": False,
    }


def resolve_provider_chain(
    provider: str = "auto",
    zone_meta: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """Construye la lista ordenada de proveedores DEM a intentar."""
    zmeta = zone_meta or {}
    chain: List[str] = []

    if provider == "auto":
        preferred = zmeta.get("preferred_dem")
        if preferred:
            chain.append(str(preferred))
        for p in settings.dem_fallback_chain:
            if p not in chain:
                chain.append(p)
    else:
        chain.append(provider)
        for p in settings.dem_fallback_chain:
            if p not in chain:
                chain.append(p)
    return chain


def fetch_dem_window(
    bbox_wgs84: Tuple[float, float, float, float],
    out_wgs84_tif: Path,
    provider: str = "auto",
    zone_meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Intenta descargar únicamente el recorte `bbox_wgs84` recorriendo la cadena de proveedores DEM.

    Returns:
        Diccionario con `path`, `provider_used`, `native_resolution_m` e `is_synthetic_fallback`.
    """
    chain = resolve_provider_chain(provider=provider, zone_meta=zone_meta)
    zmeta = zone_meta or {}
    errors: List[str] = []

    for prov in chain:
        try:
            if prov == "copernicus_aws":
                return _fetch_copernicus_aws(bbox_wgs84, out_wgs84_tif, zmeta)
            if prov == "planetary_stac":
                return _fetch_planetary_stac(
                    bbox_wgs84, out_wgs84_tif, collection="cop-dem-glo-30", provider_label="planetary_stac"
                )
            if prov == "alos_aw3d30":
                return _fetch_planetary_stac(
                    bbox_wgs84, out_wgs84_tif, collection="alos-dem", provider_label="alos_aw3d30"
                )
            if prov == "fabdem":
                return _fetch_fabdem(bbox_wgs84, out_wgs84_tif)
            if prov == "ign_wcs":
                return _fetch_ign_wcs(bbox_wgs84, out_wgs84_tif)
        except Exception as exc:
            errors.append(f"{prov}: {exc}")
            logger.debug("Proveedor DEM '%s' falló: %s", prov, exc)

    raise RuntimeError("Todos los proveedores DEM fallaron -> " + " | ".join(errors))
