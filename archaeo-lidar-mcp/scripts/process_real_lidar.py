#!/usr/bin/env python3
"""Script de conveniencia para procesar archivos LiDAR reales (.laz/.las) con ArchaeoLiDAR-AR-MCP.

Uso:
    python scripts/process_real_lidar.py data/raw/mi_archivo.laz
    python scripts/process_real_lidar.py data/raw/mi_archivo.las --resolution 0.5 --radius 12.0
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Agregar raíz del proyecto al sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import settings
from src.server import tool_run_full_pipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pipeline autónomo de prospección arqueológica LiDAR para Argentina (ArchaeoLiDAR-AR-MCP)."
    )
    parser.add_argument(
        "input_path",
        type=str,
        help="Ruta al archivo LiDAR (.las/.laz) o DTM (.tif) a procesar.",
    )
    parser.add_argument(
        "--resolution",
        type=float,
        default=0.5,
        help="Resolución espacial del DTM de salida en metros (por defecto: 0.5 m).",
    )
    parser.add_argument(
        "--radius",
        type=float,
        default=10.0,
        help="Radio del filtro de tendencia local para SLRM en metros (por defecto: 10.0 m).",
    )
    parser.add_argument(
        "--known-gpkg",
        type=str,
        default=None,
        help="Ruta opcional a un archivo GeoPackage local con sitios arqueológicos registrados.",
    )
    return parser.parse_args()


async def main_async() -> None:
    args = parse_args()
    input_file = Path(args.input_path)

    if not input_file.exists():
        print(f"\n❌ Error: No se encontró el archivo de entrada '{input_file}'.")
        print("💡 Colocá tu archivo .laz o .las en 'data/raw/' y volvé a ejecutar:")
        print(f"   python scripts/process_real_lidar.py {settings.data_dir / 'tu_archivo.laz'}\n")
        sys.exit(1)

    print("\n" + "=" * 70)
    print("🏔️  INICIANDO PIPELINE AUTÓNOMO ARCHEOLIDAR-AR-MCP")
    print("=" * 70)
    print(f"📂 Archivo de entrada: {input_file.resolve()}")
    print(f"📏 Resolución:        {args.resolution} m/px")
    print(f"🔍 Radio SLRM:         {args.radius} m")
    print("=" * 70 + "\n")

    try:
        result = await tool_run_full_pipeline(
            input_path=str(input_file),
            resolution=args.resolution,
            radius_m=args.radius,
            known_gpkg_path=args.known_gpkg,
        )

        print("\n✅ PROCESAMIENTO COMPLETADO EXITOSAMENTE")
        print("-" * 70)
        print(f"🗺️  DTM GeoTIFF (POSGAR 2007): {result['dtm_path']}")
        print(f"📊 SLRM GeoTIFF:               {result['slrm_path']}")
        print(f"📐 Slope GeoTIFF:              {result['slope_path']}")
        print(f"🏛️  Faja Cartográfica:          EPSG:{result['crs_epsg']}")
        print(f"🎯 Anomalías Detectadas:       {result['total_anomalies_detected']}")
        print("-" * 70)

        for c in result["candidates"]:
            print(f"\n📍 Candidato: {c['candidate_id']}")
            print(f"   - Tipología:       {c['type']}")
            print(f"   - Clasificación:   {c['classification']}")
            print(f"   - Confianza:       {c['confidence'] * 100:.1f}%")
            print(f"   - Área:            {c['area_m2']} m²")
            water_disp = f"{c['distance_to_water_m']} m" if c['distance_to_water_m'] is not None else "No determinado (sin datos IGN)"
            print(f"   - Distancia Agua:  {water_disp}")
            print(f"   - Lámina Visual:   {c['composite_image']}")
            print(f"   - Dossier INAPL:   {c['dossier_path']}")

        print("\n🔒 ANEXO CONFIDENCIAL DE COORDENADAS (LEY 25.743):")
        print(f"   {result['confidential_annex_path']}")
        print("=" * 70 + "\n")

    except Exception as exc:
        print(f"\n❌ Error durante el procesamiento: {exc}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
