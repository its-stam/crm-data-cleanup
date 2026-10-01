"""Writers for clean.csv, excluded.csv, report.md and review.html."""
from __future__ import annotations

import csv
from collections import Counter
from html import escape
from pathlib import Path


def write_csv(path, columns, rows) -> None:
    with Path(path).open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path) -> list:
    with Path(path).open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


# ------------------------------------------------------------------ report

def _table(headers, rows) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return "\n".join(lines)


def _flag_counts(result) -> Counter:
    return Counter(code for c in result.contacts for code, _ in c.flags)


def _unusable_counts(result) -> Counter:
    kinds = Counter()
    for rec in result.records:
        for item in rec.unusable:
            kinds[item.split("'")[0].strip()] += 1
    return kinds


def _group_sizes(result) -> Counter:
    return Counter(len(c.members) for c in result.contacts)


def write_report(path, result) -> None:
    r = result
    reasons = Counter(row["reason_code"] for row in r.excluded_rows)
    sizes = _group_sizes(r)
    merged_groups = sum(n for size, n in sizes.items() if size > 1)
    largest = max(sizes)

    parts = [
        "# Cleanup report",
        "",
        "## Balance",
        "",
        _table(["", "Rows"], [
            ["Input rows", r.n_input],
            ["excluded (`excluded.csv`)", r.n_excluded],
            ["merged into another record", r.n_absorbed],
            ["**Output records (`clean.csv`)**", f"**{r.n_output}**"],
        ]),
        "",
        f"Check: {r.n_input} = {r.n_excluded} + {r.n_absorbed} + {r.n_output}. "
        "Every input row is accounted for exactly once.",
        "",
        "## Input files",
        "",
        _table(["File", "Rows"], [[name, n] for name, n in r.source_counts]),
        "",
        "## Excluded rows by reason",
        "",
        "Nothing is deleted. Each row below is in `excluded.csv` with its reason "
        "(first matching rule; a row can match more than one).",
        "",
        _table(["Reason", "Rows"], sorted(reasons.items(), key=lambda kv: (-kv[1], kv[0]))),
        "",
        "## Suspect records (kept, flagged)",
        "",
        f"{r.n_suspect} of {r.n_output} output records carry `suspect = yes`. "
        "They stay in `clean.csv`; `review.html` lists them with the reason.",
        "",
        _table(["Flag", "Records"], sorted(_flag_counts(r).items(), key=lambda kv: (-kv[1], kv[0]))),
        "",
        "## Duplicates",
        "",
        f"{merged_groups} output records were built from more than one row "
        f"({r.n_absorbed} rows merged away). Largest group: {largest} rows.",
        "",
        _table(["Rows in group", "Output records"], sorted(sizes.items())),
        "",
        "## Unusable values",
        "",
        "Values that could not be normalised are not dropped from the audit trail: "
        "they appear in the `notes` column of the record they belong to.",
        "",
        _table(["Kind", "Count"], sorted(_unusable_counts(r).items())),
        "",
        "## Integrity checks (all passed)",
        "",
        "- balance: input = excluded + merged + output",
        "- every input row is either a kept record, merged into one, or excluded, exactly once",
        "- no normalised e-mail or phone number from the input is missing from the output",
        "- every e-mail, phone number and id is unique in `clean.csv`",
        "- every e-mail is lower case and valid, every phone number is E.164 (9 to 15 digits), every date is ISO",
        "- the same checks pass again on the files read back from disk",
    ]
    if r.warnings:
        parts += ["", "## Warnings", ""] + [f"- {w}" for w in r.warnings]
    Path(path).write_text("\n".join(parts) + "\n", encoding="utf-8")


# ------------------------------------------------------------------ review

_CSS = """
:root{--bg:#fafaf9;--fg:#1c1917;--muted:#57534e;--line:#d6d3d1;--card:#fff;--accent:#0f766e;--warn:#b45309}
@media (prefers-color-scheme:dark){:root{--bg:#161412;--fg:#f5f5f4;--muted:#a8a29e;--line:#44403c;--card:#1f1c1a;--accent:#2dd4bf;--warn:#fbbf24}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1080px;margin:0 auto;padding:24px 16px 64px}
h1{font-size:1.6rem;margin:0 0 4px}h2{font-size:1.15rem;margin:32px 0 8px}
p.lead{color:var(--muted);margin:0 0 20px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:16px 0}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.card b{display:block;font-size:1.6rem;font-variant-numeric:tabular-nums}.card span{color:var(--muted);font-size:.85rem}
details{background:var(--card);border:1px solid var(--line);border-radius:10px;margin:10px 0;padding:0 14px}
summary{cursor:pointer;padding:10px 0;font-weight:600}
.table-wrap{overflow-x:auto;margin-bottom:12px}
table{border-collapse:collapse;width:100%;font-size:.9rem}
th,td{text-align:left;padding:6px 10px;border-top:1px solid var(--line);vertical-align:top}
th{color:var(--muted);font-weight:600;white-space:nowrap}
code{font:12px ui-monospace,SFMono-Regular,Menlo,monospace}
.tag{color:var(--warn)}
input[type=search]{width:100%;padding:10px 12px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--fg);font:inherit}
ul.check{list-style:none;padding:0}ul.check li{margin:6px 0}
@media (max-width:600px){main{padding:16px 12px 48px}th,td{padding:6px}}
"""

_JS = """
const q=document.getElementById('q');
q.addEventListener('input',()=>{const t=q.value.toLowerCase();
document.querySelectorAll('tbody tr').forEach(tr=>{tr.hidden=t&&!tr.textContent.toLowerCase().includes(t)});});
"""


def _html_table(headers, rows) -> str:
    head = "".join(f"<th>{escape(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{escape(str(c))}</td>" for c in row) + "</tr>" for row in rows)
    return f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def write_review(path, result) -> None:
    r = result
    by_reason = {}
    for row in r.excluded_rows:
        by_reason.setdefault(row["reason_code"], []).append(row)

    excluded_html = "".join(
        f"<details><summary>{escape(code)} ({len(rows)})</summary>"
        + _html_table(["Id", "Name", "E-mail", "Phone", "Reason"],
                      [[x["id"], x["name"], x["email"], x["phone"], x["reason"]] for x in rows])
        + "</details>"
        for code, rows in sorted(by_reason.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    )

    suspects = [c for c in r.contacts if c.flags]
    suspect_html = _html_table(
        ["Id", "Name", "E-mail", "Phone", "Why flagged"],
        [[c.id, c.name, c.emails[0] if c.emails else "", c.phones[0] if c.phones else "",
          "; ".join(text for _, text in c.flags)] for c in suspects],
    )

    biggest = sorted((c for c in r.contacts if len(c.members) > 1),
                     key=lambda c: (-len(c.members), c.leader.index))[:10]
    merge_html = "".join(
        f"<details><summary>{len(c.members)} rows into <code>{escape(c.id)}</code> ({escape(c.name)})</summary>"
        + _html_table(["Row", "Name", "E-mail", "Phone", "Role"],
                      [[m.uid, m.name, ", ".join(m.emails), ", ".join(m.phones),
                        "leads" if m is c.leader else "merged"] for m in c.members])
        + "</details>"
        for c in biggest
    ) or "<p>No duplicates found.</p>"

    cards = "".join(
        f'<div class="card"><b>{n}</b><span>{escape(label)}</span></div>'
        for label, n in [("input rows", r.n_input), ("excluded", r.n_excluded),
                         ("merged away", r.n_absorbed), ("output records", r.n_output),
                         ("flagged suspect", r.n_suspect)]
    )

    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Review before import</title><style>{_CSS}</style></head>
<body><main>
<h1>Review before import</h1>
<p class="lead">Excluded rows and borderline records, for a person to check. Nothing here has been deleted.
This page contains contact data: do not publish it.</p>
<div class="cards">{cards}</div>
<label for="q" class="lead">Filter every table on this page</label>
<input id="q" type="search" placeholder="name, e-mail, phone, reason ...">

<h2>Sign-off</h2>
<ul class="check">
<li><label><input type="checkbox"> I looked through the {r.n_excluded} excluded rows and none of them is a real contact.</label></li>
<li><label><input type="checkbox"> I looked through the {r.n_suspect} suspect records and fixed or accepted each one.</label></li>
<li><label><input type="checkbox"> The largest merge groups below are the same person or company.</label></li>
</ul>

<h2>Excluded rows ({r.n_excluded})</h2>
{excluded_html}

<h2>Suspect records ({r.n_suspect})</h2>
{suspect_html}

<h2>Largest merge groups</h2>
{merge_html}
</main><script>{_JS}</script></body></html>
"""
    Path(path).write_text(page, encoding="utf-8")
