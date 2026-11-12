"""Configuración global y constantes geodésicas POSGAR 2007 para Argentina."""

import os
from pathlib import Path
from typing import Dict, List, Literal, Optional, Tuple

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Configuración estricta GDAL/VSICURL para lecturas remotas COG por HTTP Range Request (sin descargas completas)
os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
os.environ.setdefault("CPL_VSIL_CURL_ALLOWED_EXTENSIONS", ".tif,.tiff,.jp2")
os.environ.setdefault("VSI_CACHE", "TRUE")
os.environ.setdefault("VSI_CACHE_SIZE", "25000000")

# Diccionario oficial de Fajas POSGAR 2007 (Faja 1 a Faja 7) -> Código EPSG
POSGAR_2007_EPSG: Dict[int, int] = {
    1: 5343,  # Meridiano central -72° (Oeste cordillerano austral / cuyano extremo)
    2: 5344,  # Meridiano central -69° (NOA Oeste, Cuyo, Neuquén/Mendoza/San Juan/Catamarca)
    3: 5345,  # Meridiano central -66° (NOA Centro/Este, Tucumán, Salta, Jujuy, Córdoba Oeste)
    4: 5346,  # Meridiano central -63° (Centro del país, Córdoba, Santa Fe Oeste, La Pampa)
    5: 5347,  # Meridiano central -60° (Litoral, Buenos Aires, Entre Ríos, Santa Fe Este)
    6: 5348,  # Meridiano central -57° (Mesopotamia Este, Corrientes, Misiones Oeste)
    7: 5349,  # Meridiano central -54° (Misiones Este)
}

# Límites longitudinales por faja POSGAR 2007: (lon_min, lon_max)
POSGAR_2007_LON_BOUNDS: Dict[int, Tuple[float, float]] = {
    1: (-76.0, -70.5),
    2: (-70.5, -67.5),
    3: (-67.5, -64.5),
    4: (-64.5, -61.5),
    5: (-61.5, -58.5),
    6: (-58.5, -55.5),
    7: (-55.5, -52.0),
}

WGS84_EPSG: int = 4326
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Configuración del servidor ArchaeoLiDAR-AR-MCP validada con Pydantic Settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    data_dir: Path = Field(
        default=PROJECT_ROOT / "data" / "raw",
        alias="DATA_DIR",
        description="Directorio de entrada para nubes LiDAR (.las/.laz) y rasters crudos.",
    )
    processed_dir: Path = Field(
        default=PROJECT_ROOT / "data" / "processed",
        alias="PROCESSED_DIR",
        description="Directorio de salida para DTMs, modelos SLRM, Slope y láminas PNG.",
    )
    reports_dir: Path = Field(
        default=PROJECT_ROOT / "data" / "reports",
        alias="REPORTS_DIR",
        description="Directorio de salida para dossiers técnicos INAPL y anexos confidenciales.",
    )
    http_timeout_seconds: float = Field(
        default=25.0,
        alias="HTTP_TIMEOUT_SECONDS",
        description="Timeout máximo en segundos para peticiones HTTP a IGN, Overpass y OpenAlex.",
    )
    ign_wfs_url: str = Field(
        default="https://wms.ign.gob.ar/geoserver/ows",
        alias="IGN_WFS_URL",
        description="Endpoint OWS/WFS oficial del Instituto Geográfico Nacional de Argentina.",
    )
    overpass_url: str = Field(
        default="https://overpass-api.de/api/interpreter",
        alias="OVERPASS_URL",
        description="Endpoint de consulta Overpass API para OpenStreetMap.",
    )
    openalex_api_url: str = Field(
        default="https://api.openalex.org/works",
        alias="OPENALEX_API_URL",
        description="Endpoint de búsqueda académica OpenAlex API.",
    )
    semantic_scholar_api_url: str = Field(
        default="https://api.semanticscholar.org/graph/v1/paper/search",
        alias="SEMANTIC_SCHOLAR_API_URL",
        description="Endpoint de búsqueda académica Semantic Scholar API.",
    )
    known_sites_gpkg_path: Path = Field(
        default=PROJECT_ROOT / "data" / "known_sites.gpkg",
        alias="KNOWN_SITES_GPKG_PATH",
        description="Ruta opcional a un archivo GeoPackage local con sitios arqueológicos registrados.",
    )

    # Proveedores multisatélite (DEM + Óptico/Multiespectral + SAR) y topes estrictos de memoria/red
    dem_provider: Literal["auto", "copernicus_aws", "planetary_stac", "fabdem", "alos_aw3d30", "ign_wcs"] = Field(
        default="auto",
        alias="DEM_PROVIDER",
        description="Proveedor DEM preferido ('auto' selecciona según bioma).",
    )
    dem_fallback_chain: List[str] = Field(
        default_factory=lambda: ["ign_wcs", "fabdem", "copernicus_aws", "planetary_stac"],
        alias="DEM_FALLBACK_CHAIN",
        description="Orden de fallback de proveedores DEM cuando el preferido no está disponible.",
    )
    optical_provider: Literal["none", "sentinel2_stac", "xyz_tiles", "gee"] = Field(
        default="sentinel2_stac",
        alias="OPTICAL_PROVIDER",
        description="Proveedor óptico/multiespectral por candidato en Fase 4.",
    )
    earth_search_stac_url: str = Field(
        default="https://earth-search.aws.element84.com/v1",
        alias="EARTH_SEARCH_STAC_URL",
        description="Endpoint STAC público de Element 84 Earth Search (Sentinel-2 L2A).",
    )
    planetary_stac_url: str = Field(
        default="https://planetarycomputer.microsoft.com/api/stac/v1",
        alias="PLANETARY_STAC_URL",
        description="Endpoint STAC de Microsoft Planetary Computer.",
    )
    fabdem_stac_or_gee_collection: str = Field(
        default="projects/sat-io/open-datasets/FABDEM",
        alias="FABDEM_STAC_OR_GEE_COLLECTION",
        description="Colección GEE o identificador STAC de FABDEM V1-2.",
    )
    xyz_tile_url: str = Field(
        default="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        alias="XYZ_TILE_URL",
        description="Plantilla URL de teselas XYZ para chip RGB de alta resolución (Esri/IGN Argenmap).",
    )
    gee_project_id: Optional[str] = Field(
        default=None,
        alias="GEE_PROJECT_ID",
        description="ID de proyecto Google Earth Engine opcional para FABDEM/GEE.",
    )
    asf_earthdata_token: Optional[str] = Field(
        default=None,
        alias="ASF_EARTHDATA_TOKEN",
        description="Token opcional de NASA Earthdata/ASF para canal auxiliar SAR Banda L.",
    )
    max_master_side_px: int = Field(
        default=4096,
        alias="MAX_MASTER_SIDE_PX",
        description="Tope duro en píxeles por lado para el raster maestro reproyectado a POSGAR 2007.",
    )
    max_optical_chip_px: int = Field(
        default=512,
        alias="MAX_OPTICAL_CHIP_PX",
        description="Tope duro en píxeles por lado para el chip óptico RGB por candidato.",
    )
    optical_buffer_m: float = Field(
        default=150.0,
        alias="OPTICAL_BUFFER_M",
        description="Buffer métrico alrededor del bbox_posgar del candidato para el recorte óptico (~300x300 m).",
    )

    def ensure_directories(self) -> None:
        """Crea las carpetas de datos si no existen."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
