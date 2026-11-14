#!/usr/bin/env python3
"""Genera la fuente única de verdad de campañas (CAMPAIGN_MANIFEST.json y BASELINE_REPORT_V1.md)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.baseline_manifest import consolidate_campaign_manifest  # noqa: E402


def main() -> None:
    manifest = consolidate_campaign_manifest()
    print("✔ Manifiesto JSON:", manifest["manifest_json_path"])
    print("✔ Informe Baseline:", manifest["baseline_report_md_path"])
    print("   Estados:", manifest["summary"]["lifecycle_state_counts"])


if __name__ == "__main__":
    main()
