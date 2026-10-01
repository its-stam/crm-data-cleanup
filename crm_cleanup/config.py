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
        raise ConfigError(f"no [[source]] entry matches the file name {filename!r}")


def load_config(path) -> Config:
    path = Path(path)
    if not path.is_file():
        raise ConfigError(f"config file not found: {path} (pass one with --config)")
    with path.open("rb") as fh:
        raw = tomllib.load(fh)

    country_code = str(raw.get("phone", {}).get("default_country_code", "49"))
    if not country_code.isdigit():
        raise ConfigError("phone.default_country_code must contain digits only, e.g. \"49\"")

    exclude = raw.get("exclude", {})
    patterns = []
    for text in exclude.get("test_patterns", []):
        try:
            patterns.append(re.compile(text, re.I))
        except re.error as exc:
            raise ConfigError(f"invalid test pattern {text!r}: {exc}") from exc

    sources = []
    for entry in raw.get("source", []):
        columns = dict(entry.get("columns", {}))
        unknown = sorted(set(columns) - set(CANONICAL_FIELDS))
        if unknown:
            raise ConfigError(f"unknown field(s) in [source.columns]: {', '.join(unknown)}")
        if "match" not in entry:
            raise ConfigError("every [[source]] needs a 'match' pattern for the file name")
        sources.append(SourceMap(
            match=entry["match"],
            columns=columns,
            delimiter=entry.get("delimiter", ","),
            encoding=entry.get("encoding", "utf-8-sig"),
        ))
    if not sources:
        raise ConfigError("the config defines no [[source]] entry")

    return Config(
        country_code=country_code,
        internal_domains=tuple(d.lower().lstrip("@") for d in exclude.get("internal_domains", [])),
        internal_emails=frozenset(e.lower() for e in exclude.get("internal_emails", [])),
        test_patterns=tuple(patterns),
        sources=tuple(sources),
    )
