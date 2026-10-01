"""Configuration: exclusion lists and the column mapping of each source file."""
from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path

# Canonical fields a source may map. `name` or `first_name` + `last_name`.
CANONICAL_FIELDS = (
    "id", "name", "first_name", "last_name",
    "email", "email_2", "phone", "phone_2",
    "company", "city", "created",
)


class ConfigError(ValueError):
    """The configuration, or a source file measured against it, is unusable."""


@dataclass(frozen=True)
class SourceMap:
    match: str
    columns: dict
    delimiter: str = ","
    encoding: str = "utf-8-sig"


@dataclass(frozen=True)
class Config:
    country_code: str
    internal_domains: tuple
    internal_emails: frozenset
    test_patterns: tuple
    sources: tuple

    def source_for(self, filename: str) -> SourceMap:
        for source in self.sources:
            if fnmatch(filename, source.match):
                return source
        raise ConfigError(f"Kein [[source]]-Block passt zum Dateinamen {filename!r}")


def load_config(path) -> Config:
    path = Path(path)
    if not path.is_file():
        raise ConfigError(f"Konfigurationsdatei nicht gefunden: {path} (mit --config angeben)")
    with path.open("rb") as fh:
        raw = tomllib.load(fh)

    country_code = str(raw.get("phone", {}).get("default_country_code", "49"))
    if not country_code.isdigit():
        raise ConfigError("phone.default_country_code darf nur Ziffern enthalten, z. B. \"49\"")

    exclude = raw.get("exclude", {})
    patterns = []
    for text in exclude.get("test_patterns", []):
        try:
            patterns.append(re.compile(text, re.I))
        except re.error as exc:
            raise ConfigError(f"Ungültiges Testmuster {text!r}: {exc}") from exc

    sources = []
    for entry in raw.get("source", []):
        columns = dict(entry.get("columns", {}))
        unknown = sorted(set(columns) - set(CANONICAL_FIELDS))
        if unknown:
            raise ConfigError(f"Unbekannte(s) Feld(er) in [source.columns]: {', '.join(unknown)}")
        if "match" not in entry:
            raise ConfigError("Jeder [[source]]-Block braucht ein Muster 'match' für den Dateinamen")
        sources.append(SourceMap(
            match=entry["match"],
            columns=columns,
            delimiter=entry.get("delimiter", ","),
            encoding=entry.get("encoding", "utf-8-sig"),
        ))
    if not sources:
        raise ConfigError("Die Konfiguration enthält keinen [[source]]-Block")

    return Config(
        country_code=country_code,
        internal_domains=tuple(d.lower().lstrip("@") for d in exclude.get("internal_domains", [])),
        internal_emails=frozenset(e.lower() for e in exclude.get("internal_emails", [])),
        test_patterns=tuple(patterns),
        sources=tuple(sources),
    )
