"""Catálogo de sitios arqueológicos publicados para la validación de candidatos (`CANDIDATO_INEDITO`).

Fuente de datos: ``data/known_sites_published.csv`` (sitios publicados en bibliografía y de
dominio turístico/científico: Monumentos Históricos Nacionales, sitios UNESCO y yacimientos
con acceso público). Las coordenadas se almacenan **redondeadas a 3 decimales (~100 m de
precisión)**: suficiente para que un candidato a < 200 m sea reconocido como sitio ya
registrado, e insuficiente para servir como mapa de saqueo (Ley Nacional N° 25.743).

El GeoPackage se genera con ``build_known_sites_gpkg()`` y el prospector lo consulta
automáticamente vía ``spatial_validator._check_local_gpkg`` (ruta por defecto:
``settings.known_sites_gpkg_path`` = ``data/known_sites.gpkg``).
"""

from pathlib import Path
from typing import Optional, Union

import geopandas as gpd

DEFAULT_CSV_PATH: Path = Path(__file__).resolve().parents[2] / "data" / "known_sites_published.csv"

CSV_COLUMNS = [
    "name",
    "zone_id",
    "site_type",
    "era",
    "lon_wgs84",
    "lat_wgs84",
    "source",
    "sensitivity_note",
]


def build_known_sites_gpkg(
    csv_path: Optional[Union[str, Path]] = None,
    out_gpkg_path: Optional[Union[str, Path]] = None,
) -> Path:
    """Genera el GeoPackage de sitios registrados desde el CSV de sitios publicados.

    Args:
        csv_path: Ruta al CSV de sitios publicados (por defecto ``data/known_sites_published.csv``).
        out_gpkg_path: Ruta de salida del GeoPackage (por defecto ``data/known_sites.gpkg``).

    Returns:
        Ruta al GeoPackage generado, en ``EPSG:4326`` con geometría puntual.
    """
    import csv

    src_csv = Path(csv_path) if csv_path else DEFAULT_CSV_PATH
    if out_gpkg_path:
        out_path = Path(out_gpkg_path)
    else:
        out_path = src_csv.parent / "known_sites.gpkg"

    with src_csv.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    records = []
    geometries = []
    for row in rows:
        records.append(
            {
                "name": row["name"],
                "zone_id": row["zone_id"],
                "site_type": row["site_type"],
                "era": row["era"],
                "source": row["source"],
                "sensitivity_note": row["sensitivity_note"],
            }
        )
        geometries.append(
            gpd.points_from_xy(
                [round(float(row["lon_wgs84"]), 3)],
                [round(float(row["lat_wgs84"]), 3)],
            )[0]
        )

    gdf = gpd.GeoDataFrame(records, geometry=geometries, crs="EPSG:4326")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        out_path.unlink()
    gdf.to_file(out_path, driver="GPKG", layer="known_sites")
    return out_path


def load_known_sites_gpkg(gpkg_path: Union[str, Path]) -> "gpd.GeoDataFrame":
    """Lee el GeoPackage de sitios registrados como GeoDataFrame WGS84 (utilidad de auditoría)."""
    return gpd.read_file(gpkg_path)
