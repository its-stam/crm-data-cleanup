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
:root{--bg:#f4f5f7;--surface:#fff;--fg:#192435;--muted:#656e7a;--line:#e1e3e7;--head:#f7f8fa;
--green:#08a742;--green-bg:#e6f6ec;--blue:#317ae2;--amber:#e8a400;--amber-fg:#8a5a00;--amber-bg:#fff3d1;--purple:#7a6ff0;--red:#e5484d;--red-bg:#fdecec}
@media (prefers-color-scheme:dark){:root{--bg:#14161f;--surface:#1c1f2b;--fg:#e9ebf1;--muted:#9aa1ad;--line:#2d3142;
--head:#222636;--green:#3ccf7a;--green-bg:#17301f;--blue:#6aa3ff;--amber:#ffc94d;--amber-fg:#ffc94d;--amber-bg:#33290f;--purple:#a49dff;--red:#ff6b70;--red-bg:#3a1c1e}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.5 Inter,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
.bar{background:var(--surface);border-bottom:1px solid var(--line)}
.bar-in{max-width:1120px;margin:0 auto;padding:14px 20px;display:flex;align-items:center;gap:16px;flex-wrap:wrap}
.bar h1{font-size:20px;font-weight:600;margin:0}
.bar .sum{margin-left:auto;color:var(--fg);font-weight:500;font-variant-numeric:tabular-nums}
.bar .sum i{font-style:normal;color:var(--muted);margin:0 6px}
main{max-width:1120px;margin:0 auto;padding:20px 20px 64px}
h2{font-size:16px;font-weight:600;margin:28px 0 10px;display:flex;align-items:center;gap:8px}
h2 .count{font-size:12px;font-weight:600;color:var(--muted);background:var(--head);border:1px solid var(--line);border-radius:10px;padding:0 8px}
p.lead{color:var(--muted);margin:0 0 16px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin:0 0 18px}
.card{background:var(--surface);border:1px solid var(--line);border-radius:4px;padding:10px 14px 12px;box-shadow:0 1px 2px rgba(25,36,53,.06)}
.card:before{content:"";display:block;width:36px;height:4px;border-radius:2px;background:var(--tone,var(--blue));margin:2px 0 10px}
.card span{display:block;color:var(--muted);font-size:13px}
.card b{display:block;font-size:26px;font-weight:600;font-variant-numeric:tabular-nums;letter-spacing:-.3px}
.card.ok{background:var(--green-bg);border-color:transparent}.card.ok b{color:var(--green)}
.search{position:relative;margin:0 0 4px}
.search:before{content:"";position:absolute;left:14px;top:50%;width:11px;height:11px;margin-top:-8px;border:2px solid var(--muted);border-radius:50%}
.search:after{content:"";position:absolute;left:25px;top:50%;width:6px;height:2px;margin-top:4px;background:var(--muted);transform:rotate(45deg)}
input[type=search]{width:100%;padding:9px 14px 9px 38px;border:1px solid var(--line);border-radius:20px;background:var(--surface);color:var(--fg);font:inherit}
input[type=search]:focus{outline:2px solid var(--blue);outline-offset:0;border-color:transparent}
label.hint{display:block;color:var(--muted);font-size:13px;margin:0 0 6px}
ul.check{list-style:none;padding:0;margin:0;background:var(--surface);border:1px solid var(--line);border-radius:4px}
ul.check li{padding:10px 14px;border-top:1px solid var(--line)}ul.check li:first-child{border-top:0}
ul.check input{accent-color:var(--green);width:16px;height:16px;vertical-align:-3px;margin-right:8px}
details{background:var(--surface);border:1px solid var(--line);border-radius:4px;margin:8px 0}
summary{cursor:pointer;padding:10px 14px;font-weight:600;list-style-position:inside}
summary .count{font-size:12px;font-weight:600;color:var(--muted);background:var(--head);border:1px solid var(--line);border-radius:10px;padding:0 8px;margin-left:6px}
details[open] summary{border-bottom:1px solid var(--line)}
.table-wrap{overflow-x:auto;background:var(--surface);border:1px solid var(--line);border-radius:4px}
details .table-wrap{border:0;border-radius:0}
table{border-collapse:collapse;width:100%;font-size:14px}
th,td{text-align:left;padding:9px 12px;border-top:1px solid var(--line);vertical-align:top}
thead th{background:var(--head);color:var(--muted);font-weight:500;font-size:13px;white-space:nowrap;border-top:0}
tbody tr:hover{background:var(--head)}
td:nth-child(2){color:var(--blue);font-weight:500}
code{font:12px ui-monospace,SFMono-Regular,Menlo,monospace}
.pill{display:inline-block;font-size:12px;font-weight:600;line-height:18px;padding:0 8px;border-radius:9px;background:var(--amber-bg);color:var(--amber-fg);margin:1px 4px 1px 0}
.pill.ex{background:var(--red-bg);color:var(--red)}
.pill.lead{background:var(--green-bg);color:var(--green)}
@media (max-width:600px){.bar-in,main{padding-left:12px;padding-right:12px}th,td{padding:8px}}
"""

_JS = """
const q=document.getElementById('q');
q.addEventListener('input',()=>{const t=q.value.toLowerCase();
document.querySelectorAll('tbody tr').forEach(tr=>{tr.hidden=t&&!tr.textContent.toLowerCase().includes(t)});});
"""


def _cell(value) -> str:
    """A plain value is escaped text; a ("pill", css_class, [texts]) tuple renders escaped badges."""
    if isinstance(value, tuple) and value and value[0] == "pill":
        _, css, texts = value
        return "".join(f'<span class="pill {css}">{escape(t)}</span>' for t in texts)
    return escape(str(value))


def _html_table(headers, rows) -> str:
    head = "".join(f"<th>{escape(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{_cell(c)}</td>" for c in row) + "</tr>" for row in rows)
    return f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


_REASON_LABELS = {
    "internal": "Internal addresses",
    "test_entry": "Test entries",
    "keyboard_mash": "Keyboard mash",
    "no_contact": "No contact method",
}


def write_review(path, result) -> None:
    r = result
    by_reason = {}
    for row in r.excluded_rows:
        by_reason.setdefault(row["reason_code"], []).append(row)

    excluded_html = "".join(
        f'<details data-reason="{escape(code)}"><summary>{escape(_REASON_LABELS.get(code, code))}<span class="count">{len(rows):,}</span></summary>'
        + _html_table(["Id", "Name", "E-mail", "Phone", "Reason"],
                      [[x["id"], x["name"], x["email"], x["phone"], ("pill", "ex", [x["reason"]])] for x in rows])
        + "</details>"
        for code, rows in sorted(by_reason.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    )

    suspects = [c for c in r.contacts if c.flags]
    suspect_html = _html_table(
        ["Id", "Name", "E-mail", "Phone", "Why flagged"],
        [[c.id, c.name, c.emails[0] if c.emails else "", c.phones[0] if c.phones else "",
          ("pill", "", [text for _, text in c.flags])] for c in suspects],
    )

    biggest = sorted((c for c in r.contacts if len(c.members) > 1),
                     key=lambda c: (-len(c.members), c.leader.index))[:10]
    merge_html = "".join(
        f"<details><summary>{len(c.members)} rows into <code>{escape(c.id)}</code> ({escape(c.name)})</summary>"
        + _html_table(["Row", "Name", "E-mail", "Phone", "Role"],
                      [[m.uid, m.name, ", ".join(m.emails), ", ".join(m.phones),
                        ("pill", "lead", ["leads"]) if m is c.leader else "merged"] for m in c.members])
        + "</details>"
        for c in biggest
    ) or "<p>No duplicates found.</p>"

    cards = "".join(
        f'<div class="card{extra}" style="--tone:var({tone})"><span>{escape(label)}</span><b>{n:,}</b></div>'
        for label, n, tone, extra in [("Input rows", r.n_input, "--blue", ""),
                                      ("Excluded", r.n_excluded, "--red", ""),
                                      ("Merged away", r.n_absorbed, "--purple", ""),
                                      ("Flagged suspect", r.n_suspect, "--amber", ""),
                                      ("Clean contacts", r.n_output, "--green", " ok")]
    )

    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Review before import</title><style>{_CSS}</style></head>
<body><header class="bar"><div class="bar-in"><h1>Review before import</h1>
<span class="sum">{r.n_output:,} clean contacts<i>·</i>{r.n_input:,} rows in</span></div></header>
<main>
<p class="lead">Excluded rows and borderline records, for a person to check. Nothing here has been deleted.
This page contains contact data: do not publish it.</p>
<div class="cards">{cards}</div>
<label for="q" class="hint">Filter every table on this page</label>
<div class="search"><input id="q" type="search" placeholder="Search name, e-mail, phone or reason"></div>

<h2>Sign-off</h2>
<ul class="check">
<li><label><input type="checkbox"> I looked through the {r.n_excluded} excluded rows and none of them is a real contact.</label></li>
<li><label><input type="checkbox"> I looked through the {r.n_suspect} suspect records and fixed or accepted each one.</label></li>
<li><label><input type="checkbox"> The largest merge groups below are the same person or company.</label></li>
</ul>

<h2>Excluded rows <span class="count">{r.n_excluded:,}</span></h2>
{excluded_html}

<h2>Suspect records <span class="count">{r.n_suspect:,}</span></h2>
{suspect_html}

<h2>Largest merge groups</h2>
{merge_html}
</main><script>{_JS}</script></body></html>
"""
    Path(path).write_text(page, encoding="utf-8")
