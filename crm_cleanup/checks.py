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
            f"balance broken: {n_input} input rows != {n_excluded} excluded "
            f"+ {n_absorbed} merged + {n_output} output = {total}"
        )


@dataclass(frozen=True)
class Expected:
    """What the output must account for, taken from the loaded input rows."""
    uids: tuple
    emails: frozenset
    phones: frozenset

    @classmethod
    def from_records(cls, records) -> "Expected":
        return cls(
            uids=tuple(r.uid for r in records),
            emails=frozenset(e for r in records for e in r.emails),
            phones=frozenset(p for r in records for p in r.phones),
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
        raise IntegrityError("accounting broken: some input rows are missing or counted twice")

    # (b) no normalised e-mail or phone is lost
    out_emails = [e for row in clean_rows for e in _row_emails(row)]
    out_phones = [p for row in clean_rows for p in _row_phones(row)]
    kept_elsewhere_emails = {e for row in excluded_rows for e in split_list(row["email_normalized"])}
    kept_elsewhere_phones = {p for row in excluded_rows for p in split_list(row["phone_normalized"])}
    lost_emails = expected.emails - set(out_emails) - kept_elsewhere_emails
    lost_phones = expected.phones - set(out_phones) - kept_elsewhere_phones
    if lost_emails or lost_phones:
        raise IntegrityError(
            f"lost contact data: {len(lost_emails)} e-mail(s), {len(lost_phones)} phone number(s), "
            f"e.g. {sorted(lost_emails | lost_phones)[:3]}"
        )

    # (c) every key appears once across the output
    for label, values in (("e-mail", out_emails), ("phone", out_phones), ("id", clean_ids)):
        if len(values) != len(set(values)):
            dup = next(v for v in values if values.count(v) > 1)
            raise IntegrityError(f"{label} is not unique in the output, e.g. {dup!r}")

    # (d) formats
    for value in out_emails:
        if not is_valid_email(value) or value != value.lower():
            raise IntegrityError(f"invalid e-mail in output: {value!r}")
    for value in out_phones:
        if not is_valid_phone(value):
            raise IntegrityError(f"invalid phone number in output: {value!r}")
    for row in clean_rows:
        if row["created"] and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", row["created"]):
            raise IntegrityError(f"invalid date in output: {row['created']!r}")
        if row["suspect"] not in ("", "yes"):
            raise IntegrityError(f"invalid suspect flag: {row['suspect']!r}")
        if clean_text(row["id"]) != row["id"] or not row["id"]:
            raise IntegrityError(f"invalid id: {row['id']!r}")
