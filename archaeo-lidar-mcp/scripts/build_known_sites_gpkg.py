#!/usr/bin/env python3
"""Genera el GeoPackage de sitios arqueológicos registrados desde el CSV de sitios publicados.

Uso:
    python scripts/build_known_sites_gpkg.py [--csv data/known_sites_published.csv] [--out data/known_sites.gpkg]

El GeoPackage resultante (`data/known_sites.gpkg`, ruta por defecto de
`settings.known_sites_gpkg_path`) alimenta la validación `SITIO_REGISTRADO` del
`spatial_validator` y evita que candidatos ya documentados se reporten como inéditos.

Las coordenadas del CSV son aproximadas (±100 m, 3 decimales) de sitios publicados y de
dominio turístico/científico; ver la nota de sensibilidad en cada registro (Ley 25.743).
"""

import argparse
import sys
from pathlib import Path

# Permitir ejecución directa del script: `python scripts/build_known_sites_gpkg.py`
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.known_sites import DEFAULT_CSV_PATH, build_known_sites_gpkg  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--csv",
        type=Path,
        default=DEFAULT_CSV_PATH,
        help="Ruta al CSV de sitios publicados (por defecto: data/known_sites_published.csv).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Ruta de salida del GeoPackage (por defecto: data/known_sites.gpkg junto al CSV).",
    )
    args = parser.parse_args()

    out_path = build_known_sites_gpkg(csv_path=args.csv, out_gpkg_path=args.out)
    print(f"✔ GeoPackage de sitios registrados generado: {out_path}")


if __name__ == "__main__":
    main()
