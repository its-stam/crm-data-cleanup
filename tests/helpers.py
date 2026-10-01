"""Small builders shared by the tests."""
import csv
import re
from pathlib import Path

from crm_cleanup.config import Config
from crm_cleanup.records import Record

ROOT = Path(__file__).resolve().parent.parent


def make_config(**overrides) -> Config:
    values = dict(
        country_code="49",
        internal_domains=("example.org",),
        internal_emails=frozenset({"support@example.com"}),
        test_patterns=tuple(re.compile(p, re.I) for p in (r"\btest\b", r"\bmustermann\b")),
        sources=(),
    )
    values.update(overrides)
    return Config(**values)


def make_record(index=0, uid=None, name="Anna Müller", emails=(), phones=(), **fields) -> Record:
    return Record(uid=uid or f"s:{index}", source="s", row=index + 1, index=index,
                  name=name, emails=list(emails), phones=list(phones), **fields)


def write_rows(path: Path, header, rows) -> Path:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)
    return path
