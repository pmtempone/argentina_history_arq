"""Etapa 1.1 — Perfil de calidad y auditoría geoespacial para rasters DEM/DTM/DSM."""

import math
from pathlib import Path
from typing import Literal, Optional, Union

import numpy as np
import rasterio
from pydantic import BaseModel, ConfigDict, Field

ConfidenceTierLiteral = Literal[
    "HIGH_SUBMETRIC",
    "MEDIUM_AIRBORNE_5M",
    "LOW_REGIONAL_30M",
    "SYNTHETIC_UNSUITABLE",
]


class DEMQualityProfile(BaseModel):
    """Perfil de calidad y aptitud de escala de un modelo de elevación."""

    model_config = ConfigDict(extra="forbid")

    raster_path: str = Field(..., description="Ruta al GeoTIFF auditado.")
    provider_used: str = Field(..., description="Proveedor o fuente de origen declarada.")
    model_type: Literal["DSM", "DTM", "DEM"] = Field(
        default="DEM",
        description="Naturaleza física del modelo: DSM (superficie), DTM (suelo) o DEM genérico.",
    )
    crs_epsg: Optional[int] = Field(default=None, description="Código EPSG del CRS del raster.")
    grid_resolution_m: float = Field(..., gt=0.0, description="Tamaño de píxel en la grilla actual (metros).")
    native_resolution_m: float = Field(..., gt=0.0, description="Resolución física nativa real del sensor (metros).")
    estimated_vertical_precision_m: float = Field(
        ..., gt=0.0, description="Precisión altimétrica vertical estimada (± metros)."
    )
    width_px: int = Field(..., gt=0)
    height_px: int = Field(..., gt=0)
    coverage_pct: float = Field(..., ge=0.0, le=100.0, description="Porcentaje de píxeles válidos no-NoData.")
    void_fraction: float = Field(..., ge=0.0, le=1.0, description="Fracción de vacíos (NoData / NaN).")
    border_nodata_fraction: float = Field(
        ..., ge=0.0, le=1.0, description="Fracción de píxeles inválidos sobre el perímetro del raster."
    )
    has_synthetic_fallback_tag: bool = Field(
        default=False,
        description="True si el GeoTIFF proviene del fallback sinusoidal sintético offline.",
    )
    min_detectable_area_m2: float = Field(
        ..., gt=0.0, description="Piso físico mínimo detectable (2 píxeles a resolución nativa)."
    )
    suitable_for_microtopography: bool = Field(
        ...,
        description="True solo para fuentes aéreas/UAV/LiDAR con resolución nativa <= 5 m y no sintéticas.",
    )
    confidence_tier: ConfidenceTierLiteral = Field(
        ..., description="Nivel de confianza geomorfológica/arqueológica según escala."
    )
    limitations_note: str = Field(..., description="Limitaciones explícitas de escala y precisión vertical.")


def _estimate_vertical_precision(native_res_m: float, provider_used: str) -> float:
    prov = provider_used.lower()
    if native_res_m <= 1.0:
        return 0.10
    if native_res_m <= 5.0:
        return 1.0
    if "ign" in prov or "mde" in prov or native_res_m >= 25.0:
        # IGN MDE-Ar v2.1 / Copernicus GLO-30 (~2 m vertical en terreno abierto/ondulado)
        return 2.0
    return 2.0


def audit_dem_quality(
    raster_path: Union[str, Path],
    provider_used: str = "unknown",
    native_resolution_m: Optional[float] = None,
    model_type: Literal["DSM", "DTM", "DEM"] = "DEM",
) -> DEMQualityProfile:
    """Inspecciona un raster DEM y construye su perfil de calidad y límites de escala."""
    rpath = Path(raster_path)
    with rasterio.open(rpath) as src:
        band = src.read(1).astype(np.float64)
        nodata = src.nodata
        tags = src.tags()
        crs_epsg = src.crs.to_epsg() if src.crs else None
        grid_res_m = float((abs(src.transform.a) + abs(src.transform.e)) / 2.0)
        width_px = int(src.width)
        height_px = int(src.height)

    invalid_mask = ~np.isfinite(band) | (band <= -9000.0)
    if nodata is not None:
        try:
            nd_val = float(nodata)
            if math.isfinite(nd_val):
                invalid_mask |= np.isclose(band, nd_val, rtol=1e-6, atol=1e-6)
        except (TypeError, ValueError):
            pass

    total_px = max(1, band.size)
    invalid_count = int(np.sum(invalid_mask))
    void_fraction = float(invalid_count / total_px)
    coverage_pct = round((1.0 - void_fraction) * 100.0, 2)

    border_mask = np.zeros_like(invalid_mask, dtype=bool)
    border_mask[0, :] = True
    border_mask[-1, :] = True
    border_mask[:, 0] = True
    border_mask[:, -1] = True
    border_total = max(1, int(np.sum(border_mask)))
    border_nodata_fraction = round(float(np.sum(invalid_mask & border_mask) / border_total), 4)

    has_synth = str(tags.get("SYNTHETIC_FALLBACK", "")).upper() == "TRUE"
    native_res = float(native_resolution_m) if native_resolution_m is not None else grid_res_m
    vert_prec = _estimate_vertical_precision(native_res, provider_used)
    min_area_m2 = round(2.0 * (native_res ** 2), 2)

    if has_synth:
        tier: ConfidenceTierLiteral = "SYNTHETIC_UNSUITABLE"
        suitable = False
        note = "Fallback sintético offline: NO apto para prospección real ni inferencia arqueológica."
    elif native_res <= 1.0:
        tier = "HIGH_SUBMETRIC"
        suitable = True
        note = f"Resolución sub-métrica ({native_res:.2f} m/px): apta para microtopografía fina (muros, pircas, pozos >= {min_area_m2} m²)."
    elif native_res <= 5.0:
        tier = "MEDIUM_AIRBORNE_5M"
        suitable = True
        note = f"Resolución media ({native_res:.1f} m/px): apta para recintos medianos y terrazas (>= {min_area_m2} m²); estructuras < 5 m sub-muestreadas."
    else:
        tier = "LOW_REGIONAL_30M"
        suitable = False
        note = (
            f"DEM regional (~{native_res:.0f} m/px, ±{vert_prec:.1f} m vertical): útil para geomorfología y macro-estructuras "
            f"(>= {min_area_m2:.0f} m²), NO apto para validar microtopografía menor."
        )

    return DEMQualityProfile(
        raster_path=str(rpath),
        provider_used=provider_used,
        model_type=model_type,
        crs_epsg=crs_epsg,
        grid_resolution_m=round(grid_res_m, 4),
        native_resolution_m=round(native_res, 4),
        estimated_vertical_precision_m=vert_prec,
        width_px=width_px,
        height_px=height_px,
        coverage_pct=coverage_pct,
        void_fraction=round(void_fraction, 4),
        border_nodata_fraction=border_nodata_fraction,
        has_synthetic_fallback_tag=has_synth,
        min_detectable_area_m2=min_area_m2,
        suitable_for_microtopography=suitable,
        confidence_tier=tier,
        limitations_note=note,
    )
