"""Deterministic, invented test data: two exports with different column names.

    python -m crm_cleanup.generate --n 2000 --seed 42 --out data/sample/

Everything is made up: example.com / example.org addresses, invented names,
phone numbers in the range +49 151 0000xxxx. The same seed always produces
byte-identical files. The generator also knows the ground truth (how many
rows are junk, how many people appear more than once), which the tests use
to check the pipeline against.
"""
from __future__ import annotations

import argparse
import csv
import random
import unicodedata
from datetime import date, timedelta
from pathlib import Path

FILE_A, HEAD_A = "crm_export_a.csv", ["Contact ID", "Full Name", "Email", "Phone", "Company", "City", "Created"]
FILE_B, HEAD_B = "crm_export_b.csv", ["Kontakt-Nr", "Vorname", "Nachname", "E-Mail", "Telefon", "Mobil", "Firma", "Ort", "Erstellt am"]

FIRST = ["Anna", "Ben", "Clara", "David", "Elif", "Felix", "Greta", "Hannes", "Ida", "Jonas", "Katharina", "Lukas",
         "Mara", "Noah", "Olivia", "Paul", "Quentin", "Rosa", "Stefan", "Tamara", "Uwe", "Vera", "Walter", "Xenia",
         "Yannik", "Zoe", "Alina", "Boris", "Carla", "Dennis", "Emma", "Fabian", "Gisela", "Heiko", "Ines", "Jakob",
         "Karin", "Leon", "Miriam", "Nils", "Ottilie", "Philipp", "Rita", "Sven", "Theresa", "Ulrike", "Viktor",
         "Wiebke", "Jana", "Timo", "Lea", "Marek", "Sabine", "Oskar", "Nadine", "Armin", "Birgit", "Cem", "Dorothea",
         "Jürgen", "Björn", "Zoë", "Käthe"]
LAST = ["Albrecht", "Bergmann", "Czerny", "Dietrich", "Engel", "Fuchs", "Graf", "Hartmann", "Ibrahim", "Jansen",
        "Keller", "Lorenz", "Maurer", "Neumann", "Ott", "Pfeiffer", "Quast", "Reimann", "Sommer", "Thiel", "Ulrich",
        "Vogel", "Winter", "Zimmer", "Arnold", "Brandt", "Conrad", "Dahl", "Eberle", "Frey", "Gebhardt", "Haas",
        "Imhof", "Jung", "Kaiser", "Lindner", "Moser", "Naumann", "Ostermann", "Peters", "Richter", "Schaefer",
        "Teufel", "Unger", "Vollmer", "Wagner", "Yilmaz", "Ziegler", "Baumgartner", "Kovacs", "Novak", "Horvat",
        "Lehmann", "Marx", "Nowak", "Roth", "Seidel", "Voigt", "Wolff", "Beck", "Krause", "Lang", "Martin", "Otto",
        "Müller", "Köhler", "Jäger", "Schröder", "Böhm", "Lüdke"]
COMPANY_A = ["Nordlicht", "Rheinblick", "Alpenglut", "Kiefernhof", "Sonnenberg", "Silberbach", "Tannenwald",
             "Morgenrot", "Steinfeld", "Lindenhof", "Wiesengrund", "Eichenau", "Bergwerk", "Seebrise", "Falkenhorst"]
COMPANY_B = ["Bau GmbH", "Haustechnik GmbH", "Elektro", "Gartenbau", "Metallbau GmbH", "Malerbetrieb",
             "Dachdecker GmbH", "Schreinerei", "Logistik KG", "Fensterbau", "Heizung & Sanitär", "Reinigung"]
CITIES = ["Hamburg", "Berlin", "München", "Köln", "Frankfurt", "Stuttgart", "Leipzig", "Dresden", "Hannover",
          "Nürnberg", "Bremen", "Essen", "Dortmund", "Freiburg", "Ulm", "Kassel", "Mainz", "Rostock", "Erfurt", "Graz"]

BAD_MAIL = ["n/a", "none", "-", "kein mail", "{local}.example.com", "{local}@@example.com", "{local}@example", "{local} at example.com"]
BAD_PHONE = ["12345", "n/a", "keine", "0151", "+49", "tel folgt", "0151 123"]
KEYBOARD_NAMES = ["Asdfg Qwert", "Qwertz Asdfg", "Asdf Hjkla"]
TEST_NAMES = ["Test Test", "Test Kunde", "Max Mustermann", "Erika Mustermann", "Dummy Kontakt"]
CONSONANTS, VOWELS = "bcdfghjklmnpqrstvwxz", "aeiou"
START, DAYS = date(2019, 1, 1), 2557  # created: 2019-01-01 .. 2025-12-31


def slug(text: str) -> str:
    text = text.lower().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    text = unicodedata.normalize("NFKD", text)
    return "".join(c for c in text if c.isascii() and c.isalnum())


class _Builder:
    def __init__(self, n: int, seed: int):
        self.rng = random.Random(seed)
        self.n = n
        self.phone_pool = list(range(1, 10000))   # xxxx = 0001 .. 9999
        self.rng.shuffle(self.phone_pool)
        self.used_locals = set()
        self.rows = []                             # drafts: dicts, one per output row

    # -- identifiers
    def phone(self) -> str:
        if not self.phone_pool:
            raise ValueError("--n ist zu groß für den Nummernbereich +49 151 0000xxxx (höchstens etwa 5000)")
        return f"1510000{self.phone_pool.pop():04d}"   # national significant number, 11 digits

    def local(self, base: str) -> str:
        candidate, k = base, 1
        while candidate in self.used_locals:
            k += 1
            candidate = f"{base}{k}"
        self.used_locals.add(candidate)
        return candidate

    def consonants(self, length: int) -> str:
        return "".join(self.rng.choice(CONSONANTS) for _ in range(length))

    # -- formatting variants of one underlying value
    def fmt_phone(self, national: str) -> str:
        a, b, c = national[:3], national[3:7], national[7:]
        if self.rng.random() < 0.03:
            return f"49{a}{b}{c}"
        return self.rng.choice([
            f"0{a} {b} {c}", f"0{a}/{b}{c}", f"0{a}-{b}-{c}", f"+49 {a} {b}{c}", f"+49 {a} {b} {c}",
            f"+49{a}{b}{c}", f"0049 {a} {b} {c}", f"+49 (0){a} {b} {c}", f"(0{a}) {b} {c}",
            f"Tel. 0{a} {b}{c}", f"0{a}{b}{c}",
        ])

    def fmt_mail(self, address: str) -> str:
        r = self.rng.random()
        if r < 0.60:
            return address
        if r < 0.80:
            return address.title()
        if r < 0.90:
            return address.upper()
        return f"  {address} "

    def fmt_name(self, text: str) -> str:
        r = self.rng.random()
        if r < 0.62:
            return text
        if r < 0.74:
            return text.upper()
        if r < 0.86:
            return text.lower()
        if r < 0.95:
            return text.replace(" ", "  ") + " "
        return text.replace(" ", " ")

    def created(self) -> date | None:
        return None if self.rng.random() < 0.05 else START + timedelta(days=self.rng.randrange(DAYS))

    # -- drafts
    def draft(self, first, last, mail=None, phones=(), company="", city="", file=None, bad_date=False, initial=False):
        self.rows.append({
            "first": first, "last": last, "mail": mail, "phones": list(phones),
            "company": company, "city": city, "created": self.created(), "bad_date": bad_date,
            "initial": initial, "file": file or ("A" if self.rng.random() < 0.55 else "B"),
        })

    def company_city(self):
        company = f"{self.rng.choice(COMPANY_A)} {self.rng.choice(COMPANY_B)}" if self.rng.random() < 0.7 else ""
        city = self.rng.choice(CITIES) if self.rng.random() < 0.8 else ""
        return company, city

    def person(self):
        first, last = self.rng.choice(FIRST), self.rng.choice(LAST)
        return first, last, *self.company_city()

    def real_entity(self, size: int) -> None:
        rng = self.rng
        first, last, company, city = self.person()
        m1 = self.local(f"{slug(first)}.{slug(last)}") + "@example.com"
        files = [rng.choice("AB")]
        for _ in range(size - 1):
            files.append(("B" if files[-1] == "A" else "A") if rng.random() < 0.8 else files[-1])

        def keep(value):  # duplicates often lack optional fields
            return value if rng.random() > 0.3 else ""

        if size == 1:
            t1, r = self.phone(), rng.random()
            if r < 0.60:
                mail, phones = m1, [t1]
            elif r < 0.78:
                mail, phones = m1, []
            elif r < 0.90:
                mail, phones = None, [t1]
            elif r < 0.95:
                mail, phones = rng.choice(BAD_MAIL).format(local=m1.partition("@")[0]), [t1]
            else:
                mail, phones = m1, [rng.choice(BAD_PHONE)]
            self.draft(first, last, mail, phones, company, city, files[0], bad_date=rng.random() < 0.01,
                       initial=rng.random() < 0.08)
            return

        t1 = self.phone()
        if size == 2:
            shares_mail = rng.random() < 0.5
            self.draft(first, last, m1, [t1], company, city, files[0])
            if shares_mail:
                extra = [self.phone()] if rng.random() < 0.4 else []
                self.draft(first, last, m1, extra, keep(company), keep(city), files[1], initial=rng.random() < 0.15)
            else:
                m2 = self.local(f"{slug(first)[0]}{slug(last)}") + "@example.com" if rng.random() < 0.4 else None
                self.draft(first, last, m2, [t1], keep(company), keep(city), files[1], initial=rng.random() < 0.15)
            return

        # size 3: a chain. Row 1 and row 3 share nothing; row 2 links them (phone, then e-mail).
        m2 = self.local(f"{slug(first)[0]}{slug(last)}") + "@example.com"
        self.draft(first, last, m1, [t1], company, city, files[0])
        self.draft(first, last, m2, [t1], keep(company), keep(city), files[1])
        self.draft(first, last, m2, [], keep(company), keep(city), files[2], initial=rng.random() < 0.2)


def build(n: int, seed: int):
    """Return (rows_a, rows_b, truth) for n rows in total, deterministic for a given seed."""
    b = _Builder(n, seed)
    rng = b.rng

    def share(p: float) -> int:
        return int(round(n * p))

    special = {
        "test": share(0.03), "internal": share(0.025), "internal_shared": share(0.005), "mash": share(0.02),
        "no_contact": share(0.015), "mash_border": share(0.015), "digits": share(0.01), "repeat": share(0.005),
        "cryptic": share(0.01), "no_name": share(0.01), "keyboard": share(0.005),
    }
    n_special = sum(special.values())
    if n_special > n:
        raise ValueError("--n ist zu klein")

    # junk that has to be set aside
    for k in range(special["test"]):
        name = rng.choice(TEST_NAMES)
        first, _, last = name.partition(" ")
        mail = f"test{k}@example.com" if rng.random() < 0.5 else f"{slug(first)}.{slug(last)}{k}@example.com"
        b.draft(first, last, mail, [b.phone()] if rng.random() < 0.4 else [])
    for _ in range(special["internal"]):
        first, last, company, city = b.person()
        b.draft(first, last, b.local(f"{slug(first)}.{slug(last)}") + "@example.org", [b.phone()] if rng.random() < 0.5 else [], company, city)
    for _ in range(special["internal_shared"]):
        mail = rng.choice(["support@example.com", "billing@example.com"])
        b.draft("Team", mail.partition("@")[0].title(), mail)
    for _ in range(special["mash"]):
        first, last = b.consonants(rng.randint(4, 7)), b.consonants(rng.randint(4, 8))
        b.draft(first.title(), last.title(), f"{first}{last}@example.com" if rng.random() < 0.6 else None, [b.phone()])
    for _ in range(special["no_contact"]):
        first, last, company, city = b.person()
        bad_mail = rng.choice(BAD_MAIL).format(local=slug(last)) if rng.random() < 0.5 else None
        bad_phone = rng.choice(BAD_PHONE) if rng.random() < 0.5 else None
        b.draft(first, last, bad_mail, [bad_phone] if bad_phone else [], company, city)

    # borderline rows that stay in but are flagged
    for _ in range(special["mash_border"]):
        def token():
            letters = [rng.choice(CONSONANTS) for _ in range(rng.randint(6, 7))]
            letters.insert(rng.randrange(len(letters) + 1), rng.choice(VOWELS))
            return "".join(letters).title()
        first, last = token(), token()
        b.draft(first, last, b.local(f"{slug(first)}.{slug(last)}") + "@example.com", [b.phone()])
    for _ in range(special["digits"]):
        first, last, company, city = b.person()
        b.draft(first, f"{last} {rng.randint(1, 9)}", b.local(f"{slug(first)}.{slug(last)}") + "@example.com", [], company, city)
    for _ in range(special["repeat"]):
        first = rng.choice(FIRST)
        b.draft(first, first, b.local(f"{slug(first)}.{slug(first)}") + "@example.com", [b.phone()])
    for _ in range(special["cryptic"]):
        first, last, company, city = b.person()
        b.draft(first, last, b.local(b.consonants(rng.randint(8, 10))) + "@example.com", [b.phone()], company, city)
    for _ in range(special["keyboard"]):
        first, _, last = rng.choice(KEYBOARD_NAMES).partition(" ")
        b.draft(first, last, b.local(f"kontakt.{rng.randint(1000, 9999)}") + "@example.com", [b.phone()])
    for _ in range(special["no_name"]):
        b.draft("", "", b.local(f"kontakt.{rng.randint(1000, 9999)}") + "@example.com", [b.phone()] if rng.random() < 0.4 else [])

    # real people, some of them more than once
    remaining, entities = n - n_special, 0
    while remaining > 0:
        size = min(remaining, rng.choices([1, 2, 3], weights=[70, 22, 8])[0])
        b.real_entity(size)
        remaining -= size
        entities += 1

    junk = sum(special[k] for k in ("test", "internal", "internal_shared", "mash", "no_contact"))
    truth = {
        "rows": n,
        "excluded": junk,                                   # rows that must end up in excluded.csv
        "absorbed": (n - n_special) - entities,             # rows that must be merged into another row
        "clean": entities + (n_special - junk),             # records that must remain
    }

    # render drafts into the two file layouts
    drafts = b.rows[:]
    rng.shuffle(drafts)
    rows_a, rows_b = [], []
    for d in drafts:
        mail = b.fmt_mail(d["mail"]) if d["mail"] and d["mail"].endswith(("@example.com", "@example.org")) else d["mail"]
        phones = [b.fmt_phone(p) if p.isdigit() and len(p) == 11 else p for p in d["phones"]]
        first, last = d["first"], d["last"]
        if d["initial"] and first:
            first = first[0] + "."
        when = d["created"]
        if d["file"] == "A":
            full = f"{first} {last}".strip()
            full = b.fmt_name(full) if full else ""
            created = "n/a" if d["bad_date"] else (when.isoformat() if when else "")
            rows_a.append([f"A-{len(rows_a) + 1:05d}", full, mail or "", phones[0] if phones else "", d["company"], d["city"], created])
        else:
            created = "31.02.2024" if d["bad_date"] else (when.strftime("%d.%m.%Y") if when else "")
            rows_b.append([f"B-{len(rows_b) + 1:05d}", b.fmt_name(first) if first else "", b.fmt_name(last) if last else "",
                           mail or "", phones[0] if phones else "", phones[1] if len(phones) > 1 else "",
                           d["company"], d["city"], created])
    return rows_a, rows_b, truth


def write_files(out_dir, rows_a, rows_b) -> list:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, head, rows in ((FILE_A, HEAD_A, rows_a), (FILE_B, HEAD_B, rows_b)):
        path = out / name
        with path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh, lineterminator="\n")
            writer.writerow(head)
            writer.writerows(rows)
        paths.append(path)
    return paths


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Erzeugt erfundene, reproduzierbare CRM-Exportdateien.")
    parser.add_argument("--n", type=int, default=2000, help="Zeilen insgesamt über beide Dateien (Standard: 2000)")
    parser.add_argument("--seed", type=int, default=42, help="Startwert; derselbe Wert erzeugt identische Dateien (Standard: 42)")
    parser.add_argument("--out", default="data/sample", help="Zielordner (Standard: data/sample)")
    args = parser.parse_args(argv)
    rows_a, rows_b, truth = build(args.n, args.seed)
    for path in write_files(args.out, rows_a, rows_b):
        print(f"geschrieben: {path}")
    print(f"{len(rows_a)} + {len(rows_b)} Zeilen, Seed {args.seed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
