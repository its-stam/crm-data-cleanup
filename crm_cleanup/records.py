"""Data containers shared by the pipeline steps."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Record:
    """One input row after loading and normalisation."""
    uid: str                 # "<file stem>:<id>", unique across all sources
    source: str              # file stem
    row: int                 # 1-based data row number in the source file
    index: int               # position in load order (deterministic tie-break)
    name: str = ""
    company: str = ""
    city: str = ""
    created: str = ""        # ISO date or ""
    emails: list = field(default_factory=list)       # valid, normalised
    phones: list = field(default_factory=list)       # valid, E.164
    raw_emails: list = field(default_factory=list)   # non-empty source values
    raw_phones: list = field(default_factory=list)
    unusable: list = field(default_factory=list)     # values that could not be normalised
    reasons: list = field(default_factory=list)      # exclusion reasons: (code, text)
    flags: list = field(default_factory=list)        # suspect flags: (code, text)

    @property
    def completeness(self) -> int:
        filled = sum(bool(x) for x in (self.name, self.company, self.city, self.created))
        return filled + len(self.emails) + len(self.phones)


@dataclass
class Contact:
    """One output record: a leading row plus everything merged into it."""
    leader: Record
    members: list            # ranked, leader first
    name: str
    company: str
    city: str
    created: str
    emails: list
    phones: list
    notes: list
    flags: list

    @property
    def id(self) -> str:
        return self.leader.uid

    @property
    def merged_from(self) -> list:
        return [m.uid for m in self.members[1:]]

    @property
    def sources(self) -> list:
        return sorted({m.source for m in self.members})
