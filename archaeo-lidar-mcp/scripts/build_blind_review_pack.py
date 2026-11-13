"""Script CLI para construir el paquete de revisión ciega para especialistas externos."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.blind_review import export_blind_review_pack  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Genera un paquete de evaluación ciega (láminas PNG sin metadatos, CSV neutral y clave secreta gitignoreada)."
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Directorio de salida (por defecto data/processed/blind_review_pack).",
    )
    parser.add_argument(
        "--max-items",
        type=int,
        default=12,
        help="Cantidad máxima de láminas ciegas a exportar (por defecto 12).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Semilla aleatoria determinística para muestreo y mezcla (por defecto 42).",
    )
    args = parser.parse_args()

    result = export_blind_review_pack(
        out_dir=args.out_dir,
        max_items=args.max_items,
        seed=args.seed,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
