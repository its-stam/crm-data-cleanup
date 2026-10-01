"""Hard integrity checks. They run on the rows exactly as written, in memory
before the files are produced and again on the files read back from disk.

A failed check raises IntegrityError (an AssertionError): the run stops and
the output must not be imported.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .normalize import clean_text, is_valid_email, is_valid_phone

LIST_SEP = " | "


class IntegrityError(AssertionError):
    pass


def split_list(cell: str) -> list:
    return [part.strip() for part in (cell or "").split("|") if part.strip()]


def check_balance(n_input: int, n_excluded: int, n_absorbed: int, n_output: int) -> None:
    """input rows = excluded + merged into another row + output records."""
    total = n_excluded + n_absorbed + n_output
    if n_input != total:
        raise IntegrityError(
            f"Bilanz verletzt: {n_input} Eingangszeilen != {n_excluded} ausgeschlossen "
            f"+ {n_absorbed} zusammengeführt + {n_output} Ausgabe = {total}"
        )


@dataclass(frozen=True)
class Expected:
    """What the output must account for, taken from the loaded input rows."""
    uids: tuple
    emails: frozenset
    phones: frozenset
    country_code: str = "49"

    @classmethod
    def from_records(cls, records, country_code: str = "49") -> "Expected":
        return cls(
            uids=tuple(r.uid for r in records),
            emails=frozenset(e for r in records for e in r.emails),
            phones=frozenset(p for r in records for p in r.phones),
            country_code=country_code,
        )


def _row_emails(row: dict) -> list:
    return [e for e in [row["email"], row["email_2"], *split_list(row["more_emails"])] if e]


def _row_phones(row: dict) -> list:
    return [p for p in [row["phone"], row["phone_2"], *split_list(row["more_phones"])] if p]


def verify(expected: Expected, clean_rows: list, excluded_rows: list) -> None:
    # (a) balance and exact accounting of every input row
    merged = [uid for row in clean_rows for uid in split_list(row["merged_from"])]
    excluded_ids = [row["id"] for row in excluded_rows]
    clean_ids = [row["id"] for row in clean_rows]
    check_balance(len(expected.uids), len(excluded_ids), len(merged), len(clean_ids))
    if sorted(clean_ids + merged + excluded_ids) != sorted(expected.uids):
        raise IntegrityError("Zuordnung verletzt: Eingangszeilen fehlen oder wurden doppelt gezählt")

    # (b) no normalised e-mail or phone is lost
    out_emails = [e for row in clean_rows for e in _row_emails(row)]
    out_phones = [p for row in clean_rows for p in _row_phones(row)]
    kept_elsewhere_emails = {e for row in excluded_rows for e in split_list(row["email_normalized"])}
    kept_elsewhere_phones = {p for row in excluded_rows for p in split_list(row["phone_normalized"])}
    lost_emails = expected.emails - set(out_emails) - kept_elsewhere_emails
    lost_phones = expected.phones - set(out_phones) - kept_elsewhere_phones
    if lost_emails or lost_phones:
        raise IntegrityError(
            f"Kontaktdaten verloren: {len(lost_emails)} E-Mail(s), {len(lost_phones)} Telefonnummer(n), "
            f"z. B. {sorted(lost_emails | lost_phones)[:3]}"
        )

    # (c) every key appears once across the output
    for label, values in (("E-Mail", out_emails), ("Telefonnummer", out_phones), ("ID", clean_ids)):
        if len(values) != len(set(values)):
            dup = next(v for v in values if values.count(v) > 1)
            raise IntegrityError(f"{label} ist in der Ausgabe nicht eindeutig, z. B. {dup!r}")

    # (d) formats
    for value in out_emails:
        if not is_valid_email(value) or value != value.lower():
            raise IntegrityError(f"Ungültige E-Mail in der Ausgabe: {value!r}")
    for value in out_phones:
        if not is_valid_phone(value, expected.country_code):
            raise IntegrityError(f"Ungültige Telefonnummer in der Ausgabe: {value!r}")
    for row in clean_rows:
        if row["created"] and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", row["created"]):
            raise IntegrityError(f"Ungültiges Datum in der Ausgabe: {row['created']!r}")
        if row["suspect"] not in ("", "yes"):
            raise IntegrityError(f"Ungültige Markierung in der Spalte suspect: {row['suspect']!r}")
        if clean_text(row["id"]) != row["id"] or not row["id"]:
            raise IntegrityError(f"Ungültige ID: {row['id']!r}")
