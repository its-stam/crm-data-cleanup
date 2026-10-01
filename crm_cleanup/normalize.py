"""Field normalisation: whitespace, e-mail, phone (E.164), names, dates.

Pure functions, standard library only. Every function returns an empty
string (or None) for input it cannot turn into a valid value; the caller
decides what to do with the raw value, nothing is dropped silently here.
"""
from __future__ import annotations

import re
from datetime import date, datetime

_SPACE = re.compile(r"\s+")
_INVISIBLE = {ord(c): None for c in "​‌‍⁠﻿"}


def clean_text(value) -> str:
    """Collapse all whitespace (including non-breaking spaces) and strip the ends."""
    if value is None:
        return ""
    return _SPACE.sub(" ", str(value).translate(_INVISIBLE)).strip()


# ---------------------------------------------------------------- e-mail

# Pragmatic subset of RFC 5322: ASCII local part without leading, trailing or
# doubled dots; domain labels may contain non-ASCII letters (internationalised
# domains); the top-level domain has at least two letters and no digits.
_LABEL = r"[^\W_]+(?:-+[^\W_]+)*"          # "--" allowed: punycode labels such as xn--gebude-0ra
_TLD = r"(?:[^\W\d_]{2,}|xn--[a-z0-9-]*[a-z0-9])"
_MAIL_RE = re.compile(rf"[a-z0-9_%+'-]+(?:\.[a-z0-9_%+'-]+)*@(?:{_LABEL}\.)+{_TLD}")
_ANGLE = re.compile(r"<\s*([^<>\s]+)\s*>")


def normalize_email(raw) -> str:
    """Lower-case, trimmed, valid address, or '' if the value is not an address."""
    value = clean_text(raw).lower()
    angle = _ANGLE.search(value)           # 'John Doe <john@example.com>'
    value = (angle.group(1) if angle else value).strip("<> ")
    if value.startswith("mailto:"):
        value = value[len("mailto:"):]
    value = value.rstrip(".,; ")
    return value if _MAIL_RE.fullmatch(value) else ""


def is_valid_email(value: str) -> bool:
    return bool(_MAIL_RE.fullmatch(value))


# ----------------------------------------------------------------- phone

_PHONE_LABEL = re.compile(r"^(?:tel|telefon|phone|mobil|mobile|handy|fon)\b\.?\s*:?\s*", re.I)
_TRUNK_ZERO = re.compile(r"\(\s*0\s*\)")  # "+49 (0)151 ...": optional trunk zero in brackets
_NOT_PHONE_CHARS = re.compile(r"[^\d\s+()./\-‐-―]")
_E164_RE = re.compile(r"\+[1-9]\d{8,14}")


def normalize_phone(raw, country_code: str = "49") -> str:
    """Convert a phone number to E.164 ('+<country><number>') or return ''.

    Rules, in this order:
    * a leading label such as "Tel." is removed;
    * values that still contain letters or other text are rejected (never guessed);
    * '+...' keeps its country code;
    * '00...' is an international prefix;
    * '0...' is a national number and gets the default country code, except
      '049 151 ...' (zero, country code, separator), which already has it;
    * digits that already start with the default country code are accepted
      from ten digits on (spreadsheets swallow the plus);
    * in every branch a trunk zero right behind the default country code
      ('+49 0151', '0049 0151') is dropped;
    * the result must have 9 to 15 digits.
    """
    value = _TRUNK_ZERO.sub("", _PHONE_LABEL.sub("", clean_text(raw)))
    if not value or _NOT_PHONE_CHARS.search(value):
        return ""
    digits = re.sub(r"\D", "", value)
    if not digits:
        return ""
    if value.startswith("+"):
        intl = digits
    elif digits.startswith("00"):
        intl = digits[2:]
    elif digits.startswith("0"):
        # ponytail: "04921 123456" (Emden) is a national number that starts with 049, so the
        # zero-country-code reading needs a separator right behind it. Upgrade: area-code table.
        has_code = re.match(rf"\(?0{country_code}[\s./)-]", value)
        intl = digits[1:] if has_code else country_code + digits[1:]
    elif digits.startswith(country_code) and len(digits) >= 10:
        intl = digits
    else:
        return ""
    if intl.startswith(country_code + "0"):
        intl = country_code + intl[len(country_code) + 1:]
    if intl.startswith("0") or not 9 <= len(intl) <= 15:
        return ""
    return "+" + intl


def is_valid_phone(value: str) -> bool:
    return bool(_E164_RE.fullmatch(value))


# ------------------------------------------------------------------ name

_PARTICLES = {"von", "van", "vom", "zu", "zur", "de", "der", "den", "di", "da", "du", "la", "le", "ten", "ter"}


def normalize_name(raw) -> str:
    """Collapse whitespace; fix the case only for names typed fully in upper or lower case.

    ponytail: str.title() cannot know "McDonald" or "de la Cruz"; mixed-case
    input is therefore never touched, and a few particles stay lower case.
    """
    value = clean_text(raw)
    if sum(c.isalpha() for c in value) >= 4 and (value.isupper() or value.islower()):
        words = value.lower().split(" ")
        value = " ".join(w if (i > 0 and w in _PARTICLES) else w.title() for i, w in enumerate(words))
    return value


# ------------------------------------------------------------------ date

_DATE_FORMATS = ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%d.%m.%Y", "%d.%m.%Y %H:%M")


def parse_date(raw) -> date | None:
    value = clean_text(raw)
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def iso_date(raw) -> str:
    parsed = parse_date(raw)
    return parsed.isoformat() if parsed else ""
