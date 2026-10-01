"""Writers for clean.csv, excluded.csv, report.md and review.html."""
from __future__ import annotations

import csv
from collections import Counter
from html import escape
from pathlib import Path


def format_int(n: int) -> str:
    """German thousands separator: 1326 -> 1.326."""
    return f"{n:,}".replace(",", ".")


def write_csv(path, columns, rows) -> None:
    with Path(path).open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path) -> list:
    with Path(path).open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


# ------------------------------------------------------------------ report

_REASON_LABELS = {
    "internal": "Interne Adressen",
    "test_entry": "Testeinträge",
    "keyboard_mash": "Tastatur-Müll",
    "no_contact": "Kein Kontaktweg",
}

_FLAG_LABELS = {
    "low_vowel_share": "Wenige Vokale im Namen",
    "cryptic_email": "Zufällig wirkende E-Mail",
    "digits_in_name": "Ziffern im Namen",
    "no_name": "Kein Name",
    "keyboard_pattern": "Tastaturreihen-Muster im Namen",
    "repeated_name": "Vor- und Nachname identisch",
    "odd_phone": "Auffällige Telefonnummer",
}


def _label(labels: dict, code: str) -> str:
    """German label with the unchanged code behind it, e.g. 'Interne Adressen (`internal`)'."""
    return f"{labels[code]} (`{code}`)" if code in labels else f"`{code}`"


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
    n = format_int
    reasons = Counter(row["reason_code"] for row in r.excluded_rows)
    sizes = _group_sizes(r)
    merged_groups = sum(count for size, count in sizes.items() if size > 1)
    largest = max(sizes)

    parts = [
        "# Bereinigungsbericht",
        "",
        "## Bilanz",
        "",
        _table(["", "Zeilen"], [
            ["Eingangszeilen", n(r.n_input)],
            ["ausgeschlossen (`excluded.csv`)", n(r.n_excluded)],
            ["in einen anderen Datensatz zusammengeführt", n(r.n_absorbed)],
            ["**Saubere Kontakte (`clean.csv`)**", f"**{n(r.n_output)}**"],
        ]),
        "",
        f"Probe: {n(r.n_input)} = {n(r.n_excluded)} + {n(r.n_absorbed)} + {n(r.n_output)}. "
        "Jede Eingangszeile ist genau einmal berücksichtigt.",
        "",
        "## Eingabedateien",
        "",
        _table(["Datei", "Zeilen"], [[name, n(count)] for name, count in r.source_counts]),
        "",
        "## Ausgeschlossene Zeilen nach Grund",
        "",
        "Es wird nichts gelöscht. Jede Zeile unten steht mit ihrem Grund in `excluded.csv` "
        "(erste zutreffende Regel; eine Zeile kann auf mehrere zutreffen).",
        "",
        _table(["Grund", "Zeilen"], [[_label(_REASON_LABELS, code), n(count)]
                                     for code, count in sorted(reasons.items(), key=lambda kv: (-kv[1], kv[0]))]),
        "",
        "## Verdächtige Datensätze (behalten, markiert)",
        "",
        f"{n(r.n_suspect)} von {n(r.n_output)} Ausgabedatensätzen tragen `suspect = yes`. "
        "Sie bleiben in `clean.csv`; `review.html` listet sie mit der Begründung auf.",
        "",
        _table(["Markierung", "Datensätze"], [[_label(_FLAG_LABELS, code), n(count)]
                                              for code, count in sorted(_flag_counts(r).items(), key=lambda kv: (-kv[1], kv[0]))]),
        "",
        "## Dubletten",
        "",
        f"{n(merged_groups)} Ausgabedatensätze sind aus mehr als einer Zeile entstanden "
        f"({n(r.n_absorbed)} Zeilen zusammengeführt). Größte Gruppe: {n(largest)} Zeilen.",
        "",
        _table(["Zeilen je Gruppe", "Ausgabedatensätze"], [[size, n(count)] for size, count in sorted(sizes.items())]),
        "",
        "## Unbrauchbare Werte",
        "",
        "Werte, die sich nicht normalisieren ließen, bleiben nachvollziehbar: "
        "Sie stehen in der Spalte `notes` des zugehörigen Datensatzes.",
        "",
        _table(["Art", "Anzahl"], [[kind, n(count)] for kind, count in sorted(_unusable_counts(r).items())]),
        "",
        "## Prüfungen (alle bestanden)",
        "",
        "- Bilanz: Eingangszeilen = ausgeschlossen + zusammengeführt + Ausgabe",
        "- jede Eingangszeile ist genau einmal entweder behalten, zusammengeführt oder ausgeschlossen",
        "- keine normalisierte E-Mail und keine Telefonnummer aus der Eingabe fehlt in der Ausgabe",
        "- jede E-Mail, Telefonnummer und ID ist in `clean.csv` eindeutig",
        "- jede E-Mail ist klein geschrieben und gültig, jede Telefonnummer ist E.164 (9 bis 15 Ziffern), jedes Datum ist ISO",
        "- dieselben Prüfungen bestehen noch einmal auf den von der Platte zurückgelesenen Dateien",
    ]
    if r.warnings:
        parts += ["", "## Warnungen", ""] + [f"- {w}" for w in r.warnings]
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


def write_review(path, result) -> None:
    r = result
    n = format_int
    by_reason = {}
    for row in r.excluded_rows:
        by_reason.setdefault(row["reason_code"], []).append(row)

    excluded_html = "".join(
        f'<details data-reason="{escape(code)}"><summary>{escape(_REASON_LABELS.get(code, code))}<span class="count">{n(len(rows))}</span></summary>'
        + _html_table(["ID", "Name", "E-Mail", "Telefon", "Grund"],
                      [[x["id"], x["name"], x["email"], x["phone"], ("pill", "ex", [x["reason"]])] for x in rows])
        + "</details>"
        for code, rows in sorted(by_reason.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    )

    suspects = [c for c in r.contacts if c.flags]
    suspect_html = _html_table(
        ["ID", "Name", "E-Mail", "Telefon", "Warum markiert"],
        [[c.id, c.name, c.emails[0] if c.emails else "", c.phones[0] if c.phones else "",
          ("pill", "", [text for _, text in c.flags])] for c in suspects],
    )

    biggest = sorted((c for c in r.contacts if len(c.members) > 1),
                     key=lambda c: (-len(c.members), c.leader.index))[:10]
    merge_html = "".join(
        f"<details><summary>{len(c.members)} Zeilen zu <code>{escape(c.id)}</code> ({escape(c.name)})</summary>"
        + _html_table(["Zeile", "Name", "E-Mail", "Telefon", "Rolle"],
                      [[m.uid, m.name, ", ".join(m.emails), ", ".join(m.phones),
                        ("pill", "lead", ["führt"]) if m is c.leader else "zusammengeführt"] for m in c.members])
        + "</details>"
        for c in biggest
    ) or "<p>Keine Dubletten gefunden.</p>"

    cards = "".join(
        f'<div class="card{extra}" style="--tone:var({tone})"><span>{escape(label)}</span><b>{n(count)}</b></div>'
        for label, count, tone, extra in [("Eingangszeilen", r.n_input, "--blue", ""),
                                          ("Ausgeschlossen", r.n_excluded, "--red", ""),
                                          ("Zusammengeführt", r.n_absorbed, "--purple", ""),
                                          ("Verdächtig markiert", r.n_suspect, "--amber", ""),
                                          ("Saubere Kontakte", r.n_output, "--green", " ok")]
    )

    page = f"""<!doctype html>
<html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Prüfung vor dem Import</title><style>{_CSS}</style></head>
<body><header class="bar"><div class="bar-in"><h1>Prüfung vor dem Import</h1>
<span class="sum">{n(r.n_output)} saubere Kontakte<i>·</i>{n(r.n_input)} Zeilen eingelesen</span></div></header>
<main>
<p class="lead">Ausgeschlossene Zeilen und Grenzfälle zur Prüfung durch einen Menschen. Nichts davon wurde gelöscht.
Diese Seite enthält Kontaktdaten: Bitte veröffentlichen Sie sie nicht.</p>
<div class="cards">{cards}</div>
<label for="q" class="hint">Alle Tabellen dieser Seite filtern</label>
<div class="search"><input id="q" type="search" placeholder="Name, E-Mail, Telefon oder Grund suchen"></div>

<h2>Freigabe</h2>
<ul class="check">
<li><label><input type="checkbox"> Ich habe die {n(r.n_excluded)} ausgeschlossenen Zeilen durchgesehen, keine davon ist ein echter Kontakt.</label></li>
<li><label><input type="checkbox"> Ich habe die {n(r.n_suspect)} verdächtigen Datensätze durchgesehen und jeden korrigiert oder akzeptiert.</label></li>
<li><label><input type="checkbox"> Die größten Zusammenführungsgruppen unten sind jeweils dieselbe Person oder Firma.</label></li>
</ul>

<h2>Ausgeschlossene Zeilen <span class="count">{n(r.n_excluded)}</span></h2>
{excluded_html}

<h2>Verdächtige Datensätze <span class="count">{n(r.n_suspect)}</span></h2>
{suspect_html}

<h2>Größte Zusammenführungsgruppen</h2>
{merge_html}
</main><script>{_JS}</script></body></html>
"""
    Path(path).write_text(page, encoding="utf-8")
