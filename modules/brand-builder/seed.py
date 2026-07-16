"""
EVA Brand-Builder — seed CLI.

Parses the Eva Growth Agency blueprint markdown into pipeline.json +
blueprint.json + persona configs under ~/.eva/brand_builder/ (or EVA_BRAND_DIR).

Usage:
  python modules/brand-builder/seed.py                 # seed the first pipeline
  python modules/brand-builder/seed.py --md <path>     # seed from a specific md
  python modules/brand-builder/seed.py --id my-pipe    # custom pipeline id
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from service import BrandBuilderService, FIRST_PIPELINE_ID  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed a Brand-Builder pipeline")
    parser.add_argument("--md", type=str, default=None, help="Blueprint markdown path")
    parser.add_argument("--id", type=str, default=FIRST_PIPELINE_ID, help="Pipeline id")
    args = parser.parse_args()

    svc = BrandBuilderService()
    res = svc.seed(pipeline_id=args.id, md_path=args.md)
    print(json.dumps({
        "ok": res["ok"],
        "pipeline_id": res["pipeline"]["pipeline_id"],
        "category": res["blueprint_category"],
        "blueprint_version": res["pipeline"]["blueprint_version"],
        "personas": res["personas"],
        "content_pillars": res["pipeline"]["content_pillars"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
