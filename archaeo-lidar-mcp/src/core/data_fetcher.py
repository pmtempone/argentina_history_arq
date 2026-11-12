"""Módulo de ingesta autónoma de datos de elevación real (Router DEM Multi-Proveedor / COG / STAC / WCS)."""

import logging
from pathlib import Path
from typing import Any, Dict, Tuple, Union

import numpy as np
import rasterio
from pyproj import CRS, Transformer
from rasterio.transform import from_origin
from rasterio.warp import Resampling, calculate_default_transform, reproject

from src.config import settings
from src.core.crs_manager import get_posgar_faja, is_metric_crs
from src.core.dem_providers import (
    COPERNICUS_AWS_BASE_URL,
    build_copernicus_cog_url,
    fetch_dem_window,
)

logger = logging.getLogger(__name__)

# Alias retrocompatibles de zonas unificadas
ZONE_ALIASES: Dict[str, str] = {
    "ZONA_17_VOLCAN_CHANI": "ZONA_17_CHANI",
}


def resolve_zone_key(target_zone: str) -> str:
    """Resuelve alias históricos hacia la clave canónica en TARGET_ZONES."""
    key = target_zone.upper().strip()
    return ZONE_ALIASES.get(key, key)

# Definición de Zonas Arqueológicas Objetivo (Target Bounding Boxes en el NOA, WGS84)
# Formato bbox_wgs84: (min_lon, min_lat, max_lon, max_lat)
TARGET_ZONES: Dict[str, Dict[str, Any]] = {
    "ZONA_1_TASTIL": {
        "name": "Santa Rosa de Tastil / Quebrada del Toro (Salta)",
        "province": "Salta",
        "bbox_wgs84": (-65.968, -24.460, -65.952, -24.444),
        "posgar_epsg": 5345,  # POSGAR 2007 Faja 3
        "copernicus_tile": "Copernicus_DSM_COG_10_S25_00_W066_00_DEM",
        "toponyms": ["Tastil", "Santa Rosa de Tastil", "Quebrada del Toro"],
    },
    "ZONA_2_YOCAVIL": {
        "name": "Valle de Yocavil / Santa María / Quilmes (Catamarca - Tucumán)",
        "province": "Tucumán / Catamarca",
        "bbox_wgs84": (-66.046, -26.476, -66.030, -26.460),
        "posgar_epsg": 5345,  # POSGAR 2007 Faja 3
        "copernicus_tile": "Copernicus_DSM_COG_10_S27_00_W067_00_DEM",
        "toponyms": ["Yocavil", "Quilmes", "Santa María", "Fuerte Quemado"],
    },
    "ZONA_3_TINOGASTA": {
        "name": "Región de Tinogasta / Fiambalá / Watungasta (Catamarca)",
        "province": "Catamarca",
        "bbox_wgs84": (-67.632, -28.064, -67.616, -28.048),
        "posgar_epsg": 5344,  # POSGAR 2007 Faja 2
        "copernicus_tile": "Copernicus_DSM_COG_10_S29_00_W068_00_DEM",
        "toponyms": ["Tinogasta", "Fiambalá", "Batungasta", "Watungasta", "Abaucán"],
    },
    "ZONA_4_TOLOMBON": {
        "name": "Ruinas de Tolombón / Valle Calchaquí Sur (Salta)",
        "province": "Salta",
        "bbox_wgs84": (-65.958, -26.216, -65.942, -26.200),
        "posgar_epsg": 5345,  # POSGAR 2007 Faja 3
        "copernicus_tile": "Copernicus_DSM_COG_10_S27_00_W066_00_DEM",
        "toponyms": ["Tolombón", "Cafayate", "Calchaquí"],
    },
    "ZONA_5_LAPAYA": {
        "name": "La Paya / Cachi Adentro (Salta)",
        "province": "Salta",
        "bbox_wgs84": (-66.223, -25.020, -66.207, -25.004),
        "posgar_epsg": 5345,  # POSGAR 2007 Faja 3
        "copernicus_tile": "Copernicus_DSM_COG_10_S26_00_W067_00_DEM",
        "toponyms": ["La Paya", "Cachi", "Calchaquí"],
    },
    "ZONA_6_TILCARA": {
        "name": "Pucará de Tilcara y Quebrada de Juella (Jujuy)",
        "province": "Jujuy",
        "bbox_wgs84": (-65.401, -23.595, -65.385, -23.579),
        "posgar_epsg": 5345,  # POSGAR 2007 Faja 3
        "copernicus_tile": "Copernicus_DSM_COG_10_S24_00_W066_00_DEM",
        "toponyms": ["Tilcara", "Pucará", "Juella", "Humahuaca"],
    },
    "ZONA_7_ACONQUIJA": {
        "name": "Pucará de Aconquija / Las Pircas (Catamarca - Tucumán)",
        "province": "Catamarca",
        "bbox_wgs84": (-65.953, -27.193, -65.937, -27.177),
        "posgar_epsg": 5345,  # POSGAR 2007 Faja 3
        "copernicus_tile": "Copernicus_DSM_COG_10_S28_00_W066_00_DEM",
        "toponyms": ["Aconquija", "Las Pircas", "Andalgalá"],
    },
    "ZONA_8_SHINCAL": {
        "name": "El Shincal de Quimivil (Londres - Catamarca)",
        "province": "Catamarca",
        "bbox_wgs84": (-67.183, -28.022, -67.167, -28.006),
        "posgar_epsg": 5345,  # POSGAR 2007 Faja 3
        "copernicus_tile": "Copernicus_DSM_COG_10_S29_00_W068_00_DEM",
        "toponyms": ["Shincal", "Quimivil", "Londres", "Belén"],
    },
    "ZONA_9_ALUMBRERA": {
        "name": "Pucará de La Alumbrera / Antofagasta de la Sierra (Catamarca)",
        "province": "Catamarca",
        "bbox_wgs84": (-67.418, -26.058, -67.402, -26.042),
        "posgar_epsg": 5345,  # POSGAR 2007 Faja 3
        "copernicus_tile": "Copernicus_DSM_COG_10_S27_00_W068_00_DEM",
        "toponyms": ["Antofagasta de la Sierra", "Alumbrera", "Puna"],
    },
    "ZONA_10_RINCONADA": {
        "name": "Pucará de Rinconada (Puna de Jujuy)",
        "province": "Jujuy",
        "bbox_wgs84": (-66.163, -22.428, -66.147, -22.412),
        "posgar_epsg": 5345,  # POSGAR 2007 Faja 3
        "copernicus_tile": "Copernicus_DSM_COG_10_S23_00_W067_00_DEM",
        "toponyms": ["Rinconada", "Pucará", "Puna de Jujuy"],
    },
    "ZONA_11_LACUEVA": {
        "name": "Pueblo Viejo de La Cueva (Humahuaca - Jujuy)",
        "province": "Jujuy",
        "bbox_wgs84": (-65.293, -22.928, -65.277, -22.912),
        "posgar_epsg": 5345,  # POSGAR 2007 Faja 3
        "copernicus_tile": "Copernicus_DSM_COG_10_S23_00_W066_00_DEM",
        "toponyms": ["La Cueva", "Humahuaca", "Altiplano"],
    },
    "ZONA_12_USPALLATA": {
        "name": "Tambo de Ranchillos y Tambillo (Uspallata - Mendoza)",
        "province": "Mendoza",
        "bbox_wgs84": (-69.368, -32.608, -69.352, -32.592),
        "posgar_epsg": 5344,  # POSGAR 2007 Faja 2
        "copernicus_tile": "Copernicus_DSM_COG_10_S33_00_W070_00_DEM",
        "toponyms": ["Uspallata", "Ranchillos", "Mendoza", "Qhapaq Ñan"],
    },
    "ZONA_13_SOMUNCURA": {
        "name": "Meseta de Somuncurá / Chenques y Parapetos (Río Negro)",
        "province": "Río Negro",
        "bbox_wgs84": (-67.158, -41.258, -67.142, -41.242),
        "posgar_epsg": 5345,  # POSGAR 2007 Faja 3
        "copernicus_tile": "Copernicus_DSM_COG_10_S42_00_W068_00_DEM",
        "toponyms": ["Somuncurá", "Meseta", "Chenque", "Patagonia"],
    },
    "ZONA_14_LLULLAILLACO": {
        "name": "Santuario de Altura Volcán Llullaillaco (6.739 m s.n.m. - Salta)",
        "province": "Salta",
        "bbox_wgs84": (-68.542, -24.728, -68.526, -24.712),
        "posgar_epsg": 5344,  # POSGAR 2007 Faja 2
        "copernicus_tile": "Copernicus_DSM_COG_10_S25_00_W069_00_DEM",
        "toponyms": ["Llullaillaco", "Santuario de Altura", "Puna de Atacama", "Inca"],
    },
    "ZONA_15_VOLCAN_GALAN": {
        "name": "Caldera del Volcán Galán y Laguna Diamante (4.600 m s.n.m. - Catamarca)",
        "province": "Catamarca",
        "bbox_wgs84": (-66.923, -26.003, -66.907, -25.987),
        "posgar_epsg": 5345,  # POSGAR 2007 Faja 3
        "copernicus_tile": "Copernicus_DSM_COG_10_S26_00_W067_00_DEM",
        "toponyms": ["Volcán Galán", "Laguna Diamante", "Antofagasta", "Puna"],
    },
    "ZONA_16_LAGO_BUENOS_AIRES": {
        "name": "Meseta del Lago Buenos Aires / Parapetos de Caza y Chenques (Santa Cruz)",
        "province": "Santa Cruz",
        "bbox_wgs84": (-71.358, -47.058, -71.342, -47.042),
        "posgar_epsg": 5343,  # POSGAR 2007 Faja 1
        "copernicus_tile": "Copernicus_DSM_COG_10_S48_00_W072_00_DEM",
        "toponyms": ["Lago Buenos Aires", "Meseta", "Parapeto", "Patagonia"],
    },
}

EXPANDED_TARGET_ZONES = {
    # FRENTE 1: ALTA MONTAÑA Y SANTUARIOS INCAICOS
    "ZONA_17_CHANI": {
        "name": "Santuario de Altura del Nevado de Chañi (Jujuy / Salta - 5.896 m)",
        "bbox": [-65.78, -24.08, -65.72, -24.02],
        "epsg": 5345,
        "copernicus_tile": "Copernicus_DSM_COG_10_S25_00_W066_00_DEM",
        "toponyms": ["Nevado de Chañi", "Volcán Chañi", "Santuario de Altura", "Inca", "Niño del Chañi"],
        "biome": "alta_montana",
        "slrm_radius_m": 12.0,
        "min_area_m2": 15.0,
        "max_area_m2": 1500.0,
        "min_dz_m": 0.30,
        "max_slope_deg": 32.0,
        "archaeo_context": "Plataformas ceremoniales incaicas de cumbre, tambos de ascenso y apachetas."
    },
    "ZONA_18_FAMATINA": {
        "name": "Cerro Famatina / La Mejicana (La Rioja)",
        "bbox": [-67.85, -29.05, -67.78, -28.98],
        "epsg": 5344,
        "biome": "alta_montana",
        "slrm_radius_m": 12.0,
        "min_area_m2": 15.0,
        "max_area_m2": 2000.0,
        "min_dz_m": 0.30,
        "max_slope_deg": 32.0,
        "archaeo_context": "Santuarios de altura incaicos, kanchas estatales y tramos del Qhapaq Ñan."
    },
    "ZONA_19_ACHALA": {
        "name": "Pampa de Achala / Comechingones (Córdoba)",
        "bbox": [-64.96, -31.98, -64.90, -31.92],
        "epsg": 5345,
        "biome": "sierras_centrales",
        "slrm_radius_m": 10.0,
        "min_area_m2": 12.0,
        "max_area_m2": 800.0,
        "min_dz_m": 0.20,
        "max_slope_deg": 25.0,
        "archaeo_context": "Casas-pozo semi-enterradas, corrales pircados y aleros rocosos."
    },
    "ZONA_29_SIERRA_DE_MANCHAO": {
        "name": "Sierra de Manchao / Pocho (Córdoba)",
        "bbox": [-66.435, -28.335, -66.365, -28.265],
        "epsg": 5345,
        "biome": "sierras_centrales",
        "slrm_radius_m": 10.0,
        "min_area_m2": 12.0,
        "max_area_m2": 800.0,
        "min_dz_m": 0.20,
        "max_slope_deg": 25.0,
        "archaeo_context": "Casas-pozo comechingonas semi-enterradas (relieve negativo), corrales pircados, morteros y aleros en las laderas occidentales."
    },
    "ZONA_32_TAFI_DEL_VALLE": {
        "name": "Tafí del Valle / El Mollar (Tucumán)",
        "bbox": [-65.745, -26.895, -65.675, -26.825],
        "epsg": 5345,
        "biome": "sierras_centrales",
        "preferred_dem": "copernicus_aws",
        "slrm_radius_m": 15.0,
        "min_area_m2": 20.0,
        "max_area_m2": 4000.0,
        "min_dz_m": 0.25,
        "max_slope_deg": 25.0,
        "archaeo_context": "Unidades domésticas circulares de la cultura Tafí, montículos ceremoniales, andenes agrícolas y corrales pircados en valle intermontano."
    },

    # FRENTE 2: YUNGAS Y SELVA SUBTROPICAL
    "ZONA_20_VALLE_GRANDE": {
        "name": "Yungas de Valle Grande / Santa Ana (Jujuy)",
        "bbox": [-65.02, -23.42, -64.95, -23.35],
        "epsg": 5345,
        "biome": "yungas_selva",
        "slrm_radius_m": 15.0,
        "min_area_m2": 40.0,
        "max_area_m2": 4000.0,
        "min_dz_m": 0.40,
        "max_slope_deg": 35.0,
        "archaeo_context": "Andenería agrícola prehispánica, calzadas empedradas y recintos bajo monte."
    },
    "ZONA_21_CIUDACITA": {
        "name": "Faldeo Oriental del Aconquija / Pueblo Viejo (Tucumán)",
        "bbox": [-65.98, -27.25, -65.91, -27.18],
        "epsg": 5345,
        "biome": "yungas_montana",
        "slrm_radius_m": 15.0,
        "min_area_m2": 30.0,
        "max_area_m2": 5000.0,
        "min_dz_m": 0.35,
        "max_slope_deg": 35.0,
        "archaeo_context": "Pucarás en filos de montaña, plazas amuralladas (kanchas) y recintos satélites."
    },
    "ZONA_22_TEYU_CUARE": {
        "name": "Peñón del Teyú Cuaré / San Ignacio (Misiones)",
        "bbox": [-55.60, -27.30, -55.53, -27.24],
        "epsg": 5347,
        "biome": "selva_paranaense",
        "slrm_radius_m": 20.0,
        "min_area_m2": 50.0,
        "max_area_m2": 6000.0,
        "min_dz_m": 0.30,
        "max_slope_deg": 25.0,
        "archaeo_context": "Estructuras jesuítico-guaraníes ocultas bajo canopia, hornos y zanjas."
    },

    # FRENTE 3: HUMEDALES Y LLANURAS (CERRITOS Y MONTÍCULOS ANTRÓPICOS)
    "ZONA_23_DELTA_PARANA": {
        "name": "Delta Superior del Paraná / Victoria (Entre Ríos)",
        "bbox": [-60.25, -32.75, -60.18, -32.68],
        "epsg": 5346,
        "biome": "humedal_llanura",
        "slrm_radius_m": 40.0,
        "min_area_m2": 200.0,
        "max_area_m2": 9000.0,
        "min_dz_m": 0.35,
        "max_slope_deg": 8.0,
        "archaeo_context": "Cerritos y túmulos artificiales de tierra (tradición Goya-Malabrigo / Chaná-Timbú)."
    },
    "ZONA_24_IBERA": {
        "name": "Esteros del Iberá / Lomadas Fluviales (Corrientes)",
        "bbox": [-57.25, -28.55, -57.18, -28.48],
        "epsg": 5346,
        "biome": "humedal_llanura",
        "slrm_radius_m": 40.0,
        "min_area_m2": 200.0,
        "max_area_m2": 8000.0,
        "min_dz_m": 0.30,
        "max_slope_deg": 8.0,
        "archaeo_context": "Montículos habitacionales prehispánicos sobre albardones e islas."
    },
    "ZONA_25_ANSENUZA": {
        "name": "Laguna Mar Chiquita / Desembocadura Río Dulce (Córdoba)",
        "bbox": [-62.75, -30.95, -62.68, -30.88],
        "epsg": 5345,
        "biome": "humedal_llanura",
        "slrm_radius_m": 35.0,
        "min_area_m2": 150.0,
        "max_area_m2": 6000.0,
        "min_dz_m": 0.25,
        "max_slope_deg": 10.0,
        "archaeo_context": "Estructuras monticulares costeras y asentamientos en paleocauces."
    },

    # FRENTE 4: MESETAS PATAGÓNICAS (PARAPETOS Y CHENQUES)
    "ZONA_26_STROBEL": {
        "name": "Meseta del Lago Strobel / Cardiel (Santa Cruz)",
        "bbox": [-71.25, -48.48, -71.15, -48.40],
        "epsg": 5343,
        "biome": "meseta_patagonica",
        "slrm_radius_m": 8.0,
        "min_area_m2": 6.0,
        "max_area_m2": 400.0,
        "min_dz_m": 0.25,
        "max_slope_deg": 20.0,
        "archaeo_context": "Parapetos circulares/semicirculares de caza de guanacos y chenques."
    },
    "ZONA_27_PIEDRA_PARADA": {
        "name": "Valle del Río Chubut Medio / Piedra Parada (Chubut)",
        "bbox": [-70.15, -42.70, -70.07, -42.63],
        "epsg": 5343,
        "biome": "meseta_patagonica",
        "slrm_radius_m": 8.0,
        "min_area_m2": 8.0,
        "max_area_m2": 500.0,
        "min_dz_m": 0.25,
        "max_slope_deg": 22.0,
        "archaeo_context": "Estructuras anulares de piedra y enterratorios en terrazas altas."
    },
    "ZONA_28_PAYUNIA": {
        "name": "Campo Volcánico La Payunia / Malargüe (Mendoza)",
        "bbox": [-69.05, -36.35, -68.97, -36.28],
        "epsg": 5344,
        "biome": "meseta_volcanica",
        "slrm_radius_m": 10.0,
        "min_area_m2": 10.0,
        "max_area_m2": 600.0,
        "min_dz_m": 0.25,
        "max_slope_deg": 25.0,
        "archaeo_context": "Apostaderos de caza y corrales líticos entre coladas basálticas."
    }
}

# Inyectar y normalizar catálogo extendido en TARGET_ZONES
for _zk, _zv in EXPANDED_TARGET_ZONES.items():
    _item = dict(_zv)
    if "bbox" in _item and "bbox_wgs84" not in _item:
        _item["bbox_wgs84"] = tuple(_item["bbox"])
    if "epsg" in _item and "posgar_epsg" not in _item:
        _item["posgar_epsg"] = _item["epsg"]
    if "toponyms" not in _item:
        _item["toponyms"] = [_item["name"].split("/")[0].strip()]
    TARGET_ZONES[_zk] = _item

_FOREST_WETLAND_BIOMES = {"yungas_selva", "yungas_montana", "selva_paranaense", "humedal_llanura"}
for _zk, _zv in TARGET_ZONES.items():
    if "preferred_dem" not in _zv:
        _zv["preferred_dem"] = (
            "fabdem" if _zv.get("biome") in _FOREST_WETLAND_BIOMES else "copernicus_aws"
        )


def _reproject_and_supersample_to_posgar(
    src_wgs84_path: Path,
    dst_posgar_path: Path,
    target_epsg: int,
    target_resolution_m: float = 2.0,
    max_side_px: int | None = None,
) -> Path:
    """Reproyecta un recorte DEM geográfico a POSGAR 2007 aplicando tope de tamaño por lado y DEFLATE."""
    dst_posgar_path.parent.mkdir(parents=True, exist_ok=True)
    dst_crs = rasterio.crs.CRS.from_epsg(target_epsg)
    side_cap = int(max_side_px or settings.max_master_side_px)

    with rasterio.open(src_wgs84_path) as src:
        effective_res_m = float(target_resolution_m)
        transform, width, height = calculate_default_transform(
            src.crs,
            dst_crs,
            src.width,
            src.height,
            *src.bounds,
            resolution=(effective_res_m, effective_res_m),
        )
        max_dim = max(width, height)
        if max_dim > side_cap:
            scale = max_dim / float(side_cap)
            effective_res_m = effective_res_m * scale
            transform, width, height = calculate_default_transform(
                src.crs,
                dst_crs,
                src.width,
                src.height,
                *src.bounds,
                resolution=(effective_res_m, effective_res_m),
            )
            logger.info(
                "Tope MAX_MASTER_SIDE_PX=%d aplicado: resolución ajustada a %.3f m/px (%dx%d).",
                side_cap,
                effective_res_m,
                width,
                height,
            )

        nodata_val = -9999.0
        src_arr = src.read(1).astype(np.float32)
        if src.nodata is not None:
            src_arr[np.isclose(src_arr, float(src.nodata))] = nodata_val

        dst_arr = np.full((height, width), nodata_val, dtype=np.float32)
        reproject(
            source=src_arr,
            destination=dst_arr,
            src_transform=src.transform,
            src_crs=src.crs,
            src_nodata=nodata_val,
            dst_transform=transform,
            dst_crs=dst_crs,
            dst_nodata=nodata_val,
            resampling=Resampling.cubic,
        )

        profile = src.profile.copy()
        profile.update(
            {
                "driver": "GTiff",
                "crs": dst_crs,
                "transform": transform,
                "width": width,
                "height": height,
                "dtype": "float32",
                "count": 1,
                "nodata": nodata_val,
                "compress": "deflate",
                "predictor": 3,
            }
        )
        if width >= 256 and height >= 256:
            profile.update({"tiled": True, "blockxsize": 256, "blockysize": 256})
        else:
            profile.pop("tiled", None)
            profile.pop("blockxsize", None)
            profile.pop("blockysize", None)

        with rasterio.open(dst_posgar_path, "w", **profile) as dst:
            dst.write(dst_arr, 1)
            for tag_k in ("DEM_PROVIDER", "NATIVE_RESOLUTION_M"):
                if tag_k in src.tags():
                    dst.update_tags(**{tag_k: src.tags()[tag_k]})

    return dst_posgar_path


def fetch_elevation_tile(
    target_zone: str = "ZONA_1_TASTIL",
    cache_dir: Union[str, Path] = "data/raw/",
    resolution_m: float = 2.0,
    provider: str = "auto",
    return_metadata: bool = False,
) -> Union[str, Dict[str, Any]]:
    """Descarga, valida y reproyecta automáticamente a POSGAR 2007 el tile de elevación para la zona objetivo.

    1. Verifica si el raster métrico POSGAR 2007 real (sin tag `SYNTHETIC_FALLBACK`) existe en `cache_dir`.
    2. Si no existe, ejecuta el router `fetch_dem_window()` transfiriendo únicamente el `bbox_wgs84`.
    3. Reproyecta a POSGAR 2007 respetando `MAX_MASTER_SIDE_PX = 4096` y compresión `deflate`.
    4. Si todos los proveedores fallan, genera un fallback sintético en `*_SYNTHETIC_FALLBACK_posgar_*.tif`
       con el tag `SYNTHETIC_FALLBACK="TRUE"` para no contaminar nunca la ruta de caché definitiva.
    """
    zone_key = resolve_zone_key(target_zone)
    if zone_key not in TARGET_ZONES:
        valid_keys = ", ".join(TARGET_ZONES.keys())
        raise ValueError(f"Zona objetivo '{target_zone}' no reconocida. Zonas válidas: {valid_keys}")

    zone_info = TARGET_ZONES[zone_key]
    bbox_raw = zone_info.get("bbox") or zone_info.get("bbox_wgs84")
    bbox_wgs84: Tuple[float, float, float, float] = tuple(bbox_raw)  # type: ignore
    min_lon, min_lat, max_lon, max_lat = bbox_wgs84
    center_lon = (min_lon + max_lon) / 2.0

    target_epsg: int = int(zone_info.get("epsg") or zone_info.get("posgar_epsg") or get_posgar_faja(center_lon))

    cache_path = Path(cache_dir)
    cache_path.mkdir(parents=True, exist_ok=True)

    raw_wgs84_tif = cache_path / f"{zone_key.lower()}_dem_wgs84.tif"
    posgar_tif = cache_path / f"{zone_key.lower()}_posgar_{target_epsg}.tif"
    synthetic_tif = cache_path / f"{zone_key.lower()}_SYNTHETIC_FALLBACK_posgar_{target_epsg}.tif"

    # 1. Verificar caché real existente (descartar si tiene tag SYNTHETIC_FALLBACK)
    if posgar_tif.exists():
        try:
            with rasterio.open(posgar_tif) as src:
                tags = src.tags()
                if tags.get("SYNTHETIC_FALLBACK") == "TRUE":
                    logger.warning("Caché '%s' marcado como SYNTHETIC_FALLBACK; se reintentará descarga real.", posgar_tif)
                    posgar_tif.unlink(missing_ok=True)
                elif src.crs and is_metric_crs(src.crs) and src.width > 10 and src.height > 10:
                    sample = src.read(1)
                    if not np.all(np.isnan(sample)):
                        cached_meta = {
                            "path": str(posgar_tif),
                            "provider_used": tags.get("DEM_PROVIDER", zone_info.get("preferred_dem", "copernicus_aws")),
                            "native_resolution_m": float(tags.get("NATIVE_RESOLUTION_M", 30.0)),
                            "is_synthetic_fallback": False,
                        }
                        return cached_meta if return_metadata else str(posgar_tif)
        except Exception:
            posgar_tif.unlink(missing_ok=True)

    # 2. Descargar recorte real desde el router multi-proveedor
    eff_provider = provider if provider != "auto" else settings.dem_provider
    selected_path: Path = posgar_tif
    provider_used = str(eff_provider)
    native_res_m = 30.0
    is_synthetic = False

    try:
        dem_res = fetch_dem_window(
            bbox_wgs84=bbox_wgs84,
            out_wgs84_tif=raw_wgs84_tif,
            provider=eff_provider,
            zone_meta=zone_info,
        )
        provider_used = str(dem_res["provider_used"])
        native_res_m = float(dem_res["native_resolution_m"])
        _reproject_and_supersample_to_posgar(
            src_wgs84_path=Path(dem_res["path"]),
            dst_posgar_path=posgar_tif,
            target_epsg=target_epsg,
            target_resolution_m=resolution_m,
        )
        with rasterio.open(posgar_tif, "r+") as dst:
            dst.update_tags(
                DEM_PROVIDER=provider_used,
                NATIVE_RESOLUTION_M=str(native_res_m),
            )
        selected_path = posgar_tif
    except Exception as exc:
        # Fallback determinístico de emergencia: NUNCA se guarda como posgar_tif definitivo
        to_posgar = Transformer.from_crs(CRS.from_epsg(4326), CRS.from_epsg(target_epsg), always_xy=True)
        min_x, min_y = to_posgar.transform(min_lon, min_lat)
        max_x, max_y = to_posgar.transform(max_lon, max_lat)
        width = min(settings.max_master_side_px, max(200, int(round((max_x - min_x) / resolution_m))))
        height = min(settings.max_master_side_px, max(200, int(round((max_y - min_y) / resolution_m))))
        transform = from_origin(min_x, max_y, resolution_m, resolution_m)

        cols = np.arange(width, dtype=np.float64) * resolution_m
        rows = np.arange(height, dtype=np.float64) * resolution_m
        xx, yy = np.meshgrid(cols, rows)
        z = 3080.0 + 18.0 * np.sin(xx / 120.0) + 14.0 * np.cos(yy / 110.0)

        with rasterio.open(
            synthetic_tif,
            "w",
            driver="GTiff",
            height=height,
            width=width,
            count=1,
            dtype="float32",
            crs=rasterio.crs.CRS.from_epsg(target_epsg),
            transform=transform,
            nodata=-9999.0,
            compress="deflate",
        ) as dst:
            dst.write(z.astype(np.float32), 1)
            dst.update_tags(
                SYNTHETIC_FALLBACK="TRUE",
                DEM_PROVIDER="synthetic_fallback",
                NATIVE_RESOLUTION_M="30.0",
            )
        selected_path = synthetic_tif
        provider_used = "synthetic_fallback"
        native_res_m = 30.0
        is_synthetic = True
        print(f"[WARN] Fallback offline activado en '{synthetic_tif.name}' por error de red ({exc}).")

    # 3. Validación final con rasterio
    with rasterio.open(selected_path) as verified:
        if verified.crs is None or not is_metric_crs(verified.crs):
            raise RuntimeError(f"El tile generado '{selected_path}' no posee CRS métrico POSGAR 2007 válido.")

    if return_metadata:
        return {
            "path": str(selected_path),
            "provider_used": provider_used,
            "native_resolution_m": native_res_m,
            "is_synthetic_fallback": is_synthetic,
        }
    return str(selected_path)
