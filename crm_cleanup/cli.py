"""Command line: python -m crm_cleanup run --input data/sample/*.csv --out out/"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .checks import IntegrityError
from .config import ConfigError, load_config
from .outputs import format_int
from .pipeline import run


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m crm_cleanup", description="Bereinigt CRM-Kontaktexporte vor einem Import.")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("run", help="einlesen, normalisieren, ausschließen, Dubletten zusammenführen, prüfen und Berichte schreiben")
    p.add_argument("--input", nargs="+", required=True, metavar="CSV", help="eine oder mehrere CSV-Dateien (Platzhalter erlaubt)")
    p.add_argument("--out", default="out", help="Ausgabeordner (Standard: out)")
    p.add_argument("--config", default="config.example.toml", help="Spaltenzuordnung und Ausschlusslisten (Standard: config.example.toml)")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = run(args.input, load_config(args.config), args.out)
    except ConfigError as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 2
    except IntegrityError as exc:
        print(f"PRÜFUNG FEHLGESCHLAGEN: {exc}\nDie Dateien in {Path(args.out)} dürfen nicht importiert werden.", file=sys.stderr)
        return 1
    for warning in result.warnings:
        print(f"Warnung: {warning}", file=sys.stderr)
    out = Path(args.out)
    rows = [
        ("Eingangszeilen", result.n_input, ""),
        ("Ausgeschlossen", result.n_excluded, f"-> {out / 'excluded.csv'}"),
        ("Zusammengeführt", result.n_absorbed, ""),
        ("Saubere Kontakte", result.n_output, f"-> {out / 'clean.csv'}"),
        ("  davon verdächtig", result.n_suspect, f"-> prüfen in {out / 'review.html'}"),
    ]
    for label, n, target in rows:
        print(f"{label:<20}{format_int(n):>6}   {target}".rstrip())
    print("Alle Prüfungen bestanden. Öffnen Sie review.html und geben Sie frei, bevor Sie importieren.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
