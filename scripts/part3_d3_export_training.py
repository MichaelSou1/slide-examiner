#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from slide_examiner.d3_training import export_d3_training

REPO = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=REPO / "data/part3/d3/training")
    parser.add_argument("--max-per-cell", type=int)
    args = parser.parse_args()
    print(json.dumps(export_d3_training(REPO, args.out_dir, max_per_cell=args.max_per_cell),
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
