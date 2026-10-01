"""Exclusion and suspect rules.

Excluded rows are never deleted: they are written to excluded.csv with the
reason. Borderline rows stay in the output and carry a `suspect` flag, so a
person can decide before the import.
"""
from __future__ import annotations

import re
import unicodedata

from .config import Config
from .records import Record

_VOWELS = set("aeiouyøæœ")
_KEYBOARD_ROWS = re.compile(r"asdf|sdfg|dfgh|fghj|ghjk|hjkl|qwer|qwert|yxcv|xcvb|cvbn|vbnm|rtzu|tzui")

# Vowel share (y counts as a vowel; accents are ignored) of the letters in a text.
EXCLUDE_BELOW = 0.10   # (almost) no vowel: keyboard mash, if the name is long enough, see below
SUSPECT_BELOW = 0.15   # five or more letters and about one vowel in seven: ask a human
MASH_MIN_LETTERS = 6   # shorter vowel-less names ("Plch", "Wrzl") are real surnames: flag, do not exclude
_INITIAL = re.compile(r"\w\.?")


def letters(text: str) -> str:
    """Base letters only: lower case, accents stripped, everything else removed."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in decomposed if c.isalpha() and not unicodedata.combining(c))


def name_letters(name: str) -> str:
    """Letters of a name without initials ("L." carries no vowel information)."""
    return letters(" ".join(t for t in name.split() if not _INITIAL.fullmatch(t)))


def vowel_ratio(text: str) -> float:
    base = letters(text)
    return sum(c in _VOWELS for c in base) / len(base) if base else 1.0


def _pct(ratio: float) -> str:
    """German notation: 14 %, with a space."""
    return f"{ratio:.0%}".replace("%", " %")


def _is_keyboard_mash(base: str) -> bool:
    """No vowels, and either long enough (6+ letters) or containing a keyboard-row pattern."""
    if len(base) < 4 or vowel_ratio(base) >= EXCLUDE_BELOW:
        return False
    return len(base) >= MASH_MIN_LETTERS or bool(_KEYBOARD_ROWS.search(base))


def _is_digit_pattern(number: str) -> bool:
    """All digits equal, or strictly ascending / descending (1234567890 wraps)."""
    if len(number) < 6:
        return False
    if len(set(number)) == 1:
        return True
    steps = {(int(b) - int(a)) % 10 for a, b in zip(number, number[1:])}
    return steps == {1} or steps == {9}


def _domain_matches(address: str, domains) -> bool:
    host = address.rpartition("@")[2]
    return any(host == d or host.endswith("." + d) for d in domains)


def exclusion_reasons(rec: Record, cfg: Config) -> list:
    """All exclusion reasons as (code, text), in priority order. Empty = keep."""
    reasons = []
    if any(e in cfg.internal_emails or _domain_matches(e, cfg.internal_domains) for e in rec.emails):
        reasons.append(("internal", "interne Adresse (konfigurierte Domain oder Adressliste)"))
    probes = [rec.name, rec.company, *rec.emails]
    if any(p.search(text) for p in cfg.test_patterns for text in probes if text):
        reasons.append(("test_entry", "Testeintrag (passt auf ein konfiguriertes Testmuster)"))
    base = name_letters(rec.name)
    if _is_keyboard_mash(base):
        reasons.append(("keyboard_mash", f"Tastatur-Müll (Vokalanteil {_pct(vowel_ratio(base))})"))
    if not rec.emails and not rec.phones:
        reasons.append(("no_contact", "kein nutzbarer Kontaktweg (keine gültige E-Mail, keine gültige Telefonnummer)"))
    return reasons


def suspect_flags(rec: Record, country_code: str = "49") -> list:
    """Borderline signals on a row that is kept, as (code, text)."""
    flags = []
    base = name_letters(rec.name)
    if not rec.name:
        flags.append(("no_name", "kein Name"))
    ratio = vowel_ratio(base)
    if (len(base) >= 4 and ratio < EXCLUDE_BELOW) or (len(base) >= 5 and ratio < SUSPECT_BELOW):
        flags.append(("low_vowel_share", f"Name mit wenigen Vokalen ({_pct(ratio)})"))
    if _KEYBOARD_ROWS.search(letters(rec.name)):
        flags.append(("keyboard_pattern", "Name enthält ein Tastaturreihen-Muster"))
    if re.search(r"\d", rec.name):
        flags.append(("digits_in_name", "Ziffern im Namen"))
    parts = rec.name.lower().split()
    if len(parts) == 2 and parts[0] == parts[1]:
        flags.append(("repeated_name", "Vor- und Nachname sind identisch"))
    for address in rec.emails:
        local = letters(address.partition("@")[0])
        if len(local) >= 7 and vowel_ratio(local) < 0.12:
            flags.append(("cryptic_email", "Lokalteil der E-Mail wirkt zufällig"))
            break
    for phone in rec.phones:
        national = phone[1 + len(country_code):] if phone.startswith("+" + country_code) else phone[1:]
        if _is_digit_pattern(national):
            flags.append(("odd_phone", "Die gesamte Telefonnummer ist ein Wiederholungs- oder Zahlenfolgemuster"))
            break
    return flags
