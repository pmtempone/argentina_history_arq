"""Etapa 2 — Generador CLI del Benchmark piloto curado `BENCHMARK_V1_DATASET.json`."""

import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.core.benchmark_v1 import build_curated_benchmark_v1_dataset


def main() -> None:
    res = build_curated_benchmark_v1_dataset()
    audit = res["curation_audit"]
    print(f"✔ Benchmark JSON: {res['dataset_json_path']}")
    print(f"✔ Informe Calidad: {res['quality_report_path']}")
    print(f"   Curaduría: {json.dumps(audit, ensure_ascii=False)}")


if __name__ == "__main__":
    main()
