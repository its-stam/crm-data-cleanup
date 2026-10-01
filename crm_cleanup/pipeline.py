"""The four steps: load, normalise, exclude, deduplicate. Then verify, then write."""
from __future__ import annotations

import csv
import glob
import os
from dataclasses import dataclass, field
from pathlib import Path

from . import checks, outputs
from .config import Config, ConfigError, SourceMap
from .dedupe import group_records, merge_all
from .normalize import (clean_text, iso_date, normalize_email, normalize_name,
                        normalize_phone)
from .records import Contact, Record
from .rules import exclusion_reasons, suspect_flags

CLEAN_COLUMNS = [
    "id", "name", "company", "city",
    "email", "email_2", "more_emails", "phone", "phone_2", "more_phones",
    "created", "sources", "merged_from", "suspect", "suspect_reasons", "notes",
]
EXCLUDED_COLUMNS = [
    "id", "source", "row", "name", "email", "phone",
    "email_normalized", "phone_normalized", "reason_code", "reason",
]


@dataclass
class Result:
    records: list
    excluded: list
    groups: list
    contacts: list
    clean_rows: list
    excluded_rows: list
    source_counts: list
    warnings: list = field(default_factory=list)

    @property
    def n_input(self) -> int:
        return len(self.records)

    @property
    def n_excluded(self) -> int:
        return len(self.excluded)

    @property
    def n_output(self) -> int:
        return len(self.contacts)

    @property
    def n_absorbed(self) -> int:
        return sum(len(c.members) - 1 for c in self.contacts)

    @property
    def n_suspect(self) -> int:
        return sum(1 for c in self.contacts if c.flags)


# ------------------------------------------------------------------ load

def expand_inputs(patterns) -> list:
    """Expand wildcards the shell did not expand; sorted, so the order of arguments never matters."""
    paths = []
    for pattern in patterns:
        hits = [pattern] if os.path.exists(pattern) else sorted(glob.glob(pattern))
        if not hits:
            raise ConfigError(f"no input file matches {pattern!r}")
        paths.extend(hits)
    return sorted(dict.fromkeys(paths))


def _cell(row: dict, columns: dict, field_name: str) -> str:
    header = columns.get(field_name)
    return clean_text(row.get(header)) if header else ""


def _build_record(row: dict, sm: SourceMap, cfg: Config, stem: str, number: int, index: int, uid: str) -> Record:
    c = sm.columns
    name = _cell(row, c, "name") or clean_text(f"{_cell(row, c, 'first_name')} {_cell(row, c, 'last_name')}")
    rec = Record(
        uid=uid, source=stem, row=number, index=index,
        name=normalize_name(name),
        company=_cell(row, c, "company"),
        city=_cell(row, c, "city"),
    )
    for field_name in ("email", "email_2"):
        raw = _cell(row, c, field_name)
        if not raw:
            continue
        rec.raw_emails.append(raw)
        value = normalize_email(raw)
        if value:
            if value not in rec.emails:
                rec.emails.append(value)
        else:
            rec.unusable.append(f"unusable e-mail {raw!r}")
    for field_name in ("phone", "phone_2"):
        raw = _cell(row, c, field_name)
        if not raw:
            continue
        rec.raw_phones.append(raw)
        value = normalize_phone(raw, cfg.country_code)
        if value:
            if value not in rec.phones:
                rec.phones.append(value)
        else:
            rec.unusable.append(f"unusable phone {raw!r}")
    created = _cell(row, c, "created")
    if created:
        rec.created = iso_date(created)
        if not rec.created:
            rec.unusable.append(f"unparseable date {created!r}")
    return rec


def load_records(paths, cfg: Config):
    """Load every file with its own column mapping. Returns (records, per-file counts, warnings)."""
    records, counts, warnings = [], [], []
    seen_uids = set()
    for path in paths:
        path = Path(path)
        sm = cfg.source_for(path.name)
        with path.open(encoding=sm.encoding, newline="") as fh:
            reader = csv.DictReader(fh, delimiter=sm.delimiter)
            headers = set(reader.fieldnames or [])
            missing = sorted(h for h in sm.columns.values() if h not in headers)
            if missing:
                raise ConfigError(f"{path.name}: column(s) {missing} from the config are not in the file "
                                  f"(found: {sorted(headers)})")
            n_before = len(records)
            for number, row in enumerate(reader, start=1):
                ident = _cell(row, sm.columns, "id")
                uid = f"{path.stem}:{ident}" if ident else f"{path.stem}:row{number}"
                if uid in seen_uids:
                    uid = f"{uid}@row{number}"
                    warnings.append(f"{path.name} row {number}: duplicate id, using {uid}")
                seen_uids.add(uid)
                records.append(_build_record(row, sm, cfg, path.stem, number, len(records), uid))
            counts.append((path.name, len(records) - n_before))
    return records, counts, warnings


# --------------------------------------------------------------- output rows

def _list(items) -> str:
    return checks.LIST_SEP.join(items)


def contact_row(c: Contact) -> dict:
    emails, phones = c.emails, c.phones
    return {
        "id": c.id, "name": c.name, "company": c.company, "city": c.city,
        "email": emails[0] if emails else "",
        "email_2": emails[1] if len(emails) > 1 else "",
        "more_emails": _list(emails[2:]),
        "phone": phones[0] if phones else "",
        "phone_2": phones[1] if len(phones) > 1 else "",
        "more_phones": _list(phones[2:]),
        "created": c.created,
        "sources": _list(c.sources),
        "merged_from": _list(c.merged_from),
        "suspect": "yes" if c.flags else "",
        "suspect_reasons": "; ".join(text for _, text in c.flags),
        "notes": "; ".join(c.notes),
    }


def excluded_row(rec: Record) -> dict:
    return {
        "id": rec.uid, "source": rec.source, "row": rec.row, "name": rec.name,
        "email": _list(rec.raw_emails), "phone": _list(rec.raw_phones),
        "email_normalized": _list(rec.emails), "phone_normalized": _list(rec.phones),
        "reason_code": rec.reasons[0][0],
        "reason": "; ".join(text for _, text in rec.reasons),
    }


# --------------------------------------------------------------------- run

def process(paths, cfg: Config) -> Result:
    """Steps a to d in memory, with the integrity checks. Nothing is written here."""
    records, counts, warnings = load_records(paths, cfg)

    excluded, kept = [], []
    for rec in records:
        rec.reasons = exclusion_reasons(rec, cfg)
        (excluded if rec.reasons else kept).append(rec)
    for rec in kept:
        rec.flags = suspect_flags(rec, cfg.country_code)

    # Excluded rows are set aside before matching: an internal or test row
    # must never be the link that glues two real contacts together.
    groups = group_records(kept)
    contacts = merge_all(groups)

    result = Result(
        records=records, excluded=excluded, groups=groups, contacts=contacts,
        clean_rows=[contact_row(c) for c in contacts],
        excluded_rows=[excluded_row(r) for r in excluded],
        source_counts=counts, warnings=warnings,
    )
    checks.verify(checks.Expected.from_records(records, cfg.country_code), result.clean_rows, result.excluded_rows)
    return result


def run(patterns, cfg: Config, out_dir) -> Result:
    result = process(expand_inputs(patterns), cfg)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    outputs.write_csv(out_dir / "clean.csv", CLEAN_COLUMNS, result.clean_rows)
    outputs.write_csv(out_dir / "excluded.csv", EXCLUDED_COLUMNS, result.excluded_rows)
    outputs.write_report(out_dir / "report.md", result)
    outputs.write_review(out_dir / "review.html", result)
    # Second pass on the files themselves, not on the in-memory rows.
    checks.verify(
        checks.Expected.from_records(result.records, cfg.country_code),
        outputs.read_csv(out_dir / "clean.csv"),
        outputs.read_csv(out_dir / "excluded.csv"),
    )
    return result
