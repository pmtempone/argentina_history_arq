"""Configuración global y constantes geodésicas POSGAR 2007 para Argentina."""

from pathlib import Path
from typing import Dict, Tuple

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

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


class Settings(BaseSettings):
    """Configuración del servidor ArchaeoLiDAR-AR-MCP validada con Pydantic Settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    data_dir: Path = Field(
        default=Path("./data/raw"),
        alias="DATA_DIR",
        description="Directorio de entrada para nubes LiDAR (.las/.laz) y rasters crudos.",
    )
    processed_dir: Path = Field(
        default=Path("./data/processed"),
        alias="PROCESSED_DIR",
        description="Directorio de salida para DTMs, modelos SLRM, Slope y láminas PNG.",
    )
    reports_dir: Path = Field(
        default=Path("./data/reports"),
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
        default=Path("./data/known_sites.gpkg"),
        alias="KNOWN_SITES_GPKG_PATH",
        description="Ruta opcional a un archivo GeoPackage local con sitios arqueológicos registrados.",
    )

    def ensure_directories(self) -> None:
        """Crea las carpetas de datos si no existen."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
