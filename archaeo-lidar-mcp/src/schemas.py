"""Modelos Pydantic v2 de entrada y salida para las herramientas del servidor MCP."""

from typing import Any, Dict, List, Literal, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field

AnomalyTypeLiteral = Literal[
    "recinto_ortogonal",
    "estructura_circular",
    "terraza_lineal",
    "complejo_agrupado",
]

ClassificationLiteral = Literal[
    "CANDIDATO_INEDITO",
    "SITIO_REGISTRADO",
    "FALSO_POSITIVO_MODERNO",
]


class DTMResult(BaseModel):
    """Resultado de la generación del Modelo Digital del Terreno (DTM) a partir de LiDAR."""

    model_config = ConfigDict(extra="forbid")

    status: str = Field(..., description="Estado del procesamiento (ej. 'success').")
    dtm_path: str = Field(..., description="Ruta absoluta o relativa al GeoTIFF del DTM generado.")
    crs_epsg: int = Field(..., description="Código EPSG métrico del raster de salida (POSGAR 2007).")
    resolution_m: float = Field(..., gt=0.0, description="Resolución espacial de celda en metros.")
    bounds: Tuple[float, float, float, float] = Field(
        ..., description="Bounding box métrico (minx, miny, maxx, maxy)."
    )
    point_count: int = Field(..., ge=0, description="Cantidad de puntos de suelo (Clase 2) procesados.")


class ReliefResult(BaseModel):
    """Resultado del cálculo de Modelos de Relieve Local (SLRM y Pendiente)."""

    model_config = ConfigDict(extra="forbid")

    status: str = Field(..., description="Estado del cálculo (ej. 'success').")
    slrm_path: str = Field(..., description="Ruta al GeoTIFF Float32 del Simple Local Relief Model.")
    slope_path: str = Field(..., description="Ruta al GeoTIFF Float32 de pendiente en grados.")
    stats_dict: Dict[str, float] = Field(
        ...,
        description="Estadísticas descriptivas de los modelos generados (min, max, mean, std).",
    )


class AnomalyFeature(BaseModel):
    """Representación tipada de una anomalía microtopográfica detectada por visión artificial."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., description="Identificador único del candidato arqueológico.")
    anomaly_type: AnomalyTypeLiteral = Field(
        ...,
        description="Tipología morfológica detectada (recinto_ortogonal, estructura_circular, terraza_lineal, complejo_agrupado).",
    )
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Nivel de confianza geométrica y topográfica [0.0 - 1.0]."
    )
    area_m2: float = Field(..., gt=0.0, description="Área plana en metros cuadrados calculada en POSGAR 2007.")
    rectangularity: float = Field(
        ..., ge=0.0, le=1.0, description="Índice de rectangularidad (área / área mínima caja rotada)."
    )
    circularity: float = Field(
        ..., ge=0.0, le=1.5, description="Índice de circularidad isoperimétrica (4 * pi * A / P^2)."
    )
    mean_elevation_m: float = Field(
        ..., description=" Promedio de sobre-elevación local en metros respecto a la tendencia (SLRM)."
    )
    centroid_wgs84: Tuple[float, float] = Field(
        ..., description="Coordenadas del centroide reproyectadas a WGS84 (lon, lat)."
    )
    geometry_geojson: Dict[str, Any] = Field(
        ..., description="Geometría GeoJSON del polígono reproyectada a EPSG:4326."
    )


class ValidationResult(BaseModel):
    """Resultado de la validación cruzada espacial y bibliográfica de un candidato."""

    model_config = ConfigDict(extra="forbid")

    anomaly_id: str = Field(..., description="Identificador del candidato validado.")
    classification: ClassificationLiteral = Field(
        ...,
        description="Clasificación patrimonial: CANDIDATO_INEDITO, SITIO_REGISTRADO o FALSO_POSITIVO_MODERNO.",
    )
    ign_matches: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Entidades encontradas en el WFS del Instituto Geográfico Nacional.",
    )
    osm_matches: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Elementos encontrados en OpenStreetMap vía Overpass API en un radio de 150 m.",
    )
    literature_matches: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Artículos académicos relevantes recuperados de OpenAlex / Semantic Scholar.",
    )
    distance_to_water_m: Optional[float] = Field(
        default=None,
        description="Distancia métrica en metros al curso o cuerpo de agua más cercano según IGN (None si no se determinó).",
    )


class CrossSectionResult(BaseModel):
    """Resultado de la verificación de corte transversal (cross-section) sobre la nube de puntos cruda."""

    model_config = ConfigDict(extra="forbid")

    plot_image_path: str = Field(..., description="Ruta a la imagen PNG del perfil transversal renderizado.")
    ground_points_count: int = Field(..., ge=0, description="Número de puntos clasificados como suelo (ASPRS Clase 2).")
    vegetation_points_count: int = Field(
        ..., ge=0, description="Número de puntos clasificados como vegetación (ASPRS Clases 3, 4 y 5)."
    )
    ground_density_pts_m2: float = Field(
        ..., ge=0.0, description="Densidad efectiva de retornos de suelo por metro cuadrado en la franja."
    )
    profile_integrity_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Puntaje de integridad del perfil de suelo [0.0 - 1.0] para descartar artefactos de interpolación.",
    )
