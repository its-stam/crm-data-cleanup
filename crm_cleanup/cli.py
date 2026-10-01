"""Command line: python -m crm_cleanup run --input data/sample/*.csv --out out/"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .checks import IntegrityError
from .config import ConfigError, load_config
from .pipeline import run


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m crm_cleanup", description="Clean CRM contact exports before an import.")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("run", help="load, normalise, exclude, deduplicate, verify and write the reports")
    p.add_argument("--input", nargs="+", required=True, metavar="CSV", help="one or more CSV files (wildcards allowed)")
    p.add_argument("--out", default="out", help="output folder (default: out)")
    p.add_argument("--config", default="config.example.toml", help="column mapping and exclusion lists (default: config.example.toml)")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = run(args.input, load_config(args.config), args.out)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except IntegrityError as exc:
        print(f"INTEGRITY CHECK FAILED: {exc}\nDo not import the files in {Path(args.out)}.", file=sys.stderr)
        return 1
    for warning in result.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    out = Path(args.out)
    print(f"Input rows         {result.n_input:>6}")
    print(f"Excluded           {result.n_excluded:>6}   -> {out / 'excluded.csv'}")
    print(f"Merged away        {result.n_absorbed:>6}")
    print(f"Output records     {result.n_output:>6}   -> {out / 'clean.csv'}")
    print(f"  flagged suspect  {result.n_suspect:>6}   -> check in {out / 'review.html'}")
    print("Integrity checks passed. Open review.html and sign off before importing.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
