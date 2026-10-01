"""Duplicate detection (Union-Find over normalised e-mail and phone) and merging."""
from __future__ import annotations

import re

from .records import Contact

_INITIAL_TOKEN = re.compile(r"\w\.")


class UnionFind:
    """Disjoint sets with path halving. The smaller index always becomes the root."""

    def __init__(self, size: int):
        self.parent = list(range(size))

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)


def group_records(records: list) -> list:
    """Group rows that share a normalised e-mail or phone, transitively.

    A-B share an e-mail and B-C share a phone: A, B and C form one group even
    though A and C have nothing in common. Groups are returned in order of
    their first member, members in input order.
    """
    uf = UnionFind(len(records))
    seen = {}
    for i, rec in enumerate(records):
        for key in [("m", m) for m in rec.emails] + [("t", p) for p in rec.phones]:
            if key in seen:
                uf.union(seen[key], i)
            else:
                seen[key] = i
    groups = {}
    for i, rec in enumerate(records):
        groups.setdefault(uf.find(i), []).append(rec)
    return [groups[root] for root in sorted(groups)]


def _unique(items) -> list:
    seen = set()
    return [x for x in items if not (x in seen or seen.add(x))]


def merge_group(group: list) -> Contact:
    """Merge one group. The most complete row leads; ties go to the earlier row."""
    members = sorted(group, key=lambda r: (-r.completeness, r.index))
    leader = members[0]
    emails = _unique(e for m in members for e in m.emails)
    phones = _unique(p for m in members for p in m.phones)
    # The leader's name wins, unless it is abbreviated ("L. Brandt") and another row spells it out.
    names = [m.name for m in members if m.name]
    name = next((n for n in names if not _INITIAL_TOKEN.search(n)), names[0] if names else "")
    notes = []
    for other in _unique(m.name for m in members if m.name and m.name.casefold() != name.casefold()):
        notes.append(f"auch erfasst als: {other}")
    for m in members:
        notes.extend(f"{u} ({m.uid})" for u in m.unusable)
    flags = _unique(f for m in members for f in m.flags)
    return Contact(
        leader=leader,
        members=members,
        name=name,
        company=next((m.company for m in members if m.company), ""),
        city=next((m.city for m in members if m.city), ""),
        created=min((m.created for m in members if m.created), default=""),
        emails=emails,
        phones=phones,
        notes=notes,
        flags=flags,
    )


def merge_all(groups: list) -> list:
    return [merge_group(g) for g in groups]
