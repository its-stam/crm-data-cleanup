"""Alle sichtbaren Texte sind deutsch: Konsole, Meldungen, Begründungen, Bericht und Prüfseite."""
import contextlib
import csv
import io
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from crm_cleanup import cli, generate
from crm_cleanup.checks import IntegrityError
from crm_cleanup.config import load_config
from crm_cleanup.outputs import format_int
from crm_cleanup.pipeline import run

from .helpers import ROOT

SCHLUSSZEILE = "Alle Prüfungen bestanden. Öffnen Sie review.html und geben Sie frei, bevor Sie importieren."


class FormatTest(unittest.TestCase):
    def test_thousands_separator_is_a_dot(self):
        self.assertEqual([format_int(n) for n in (0, 999, 1000, 1326, 2000, 1234567)],
                         ["0", "999", "1.000", "1.326", "2.000", "1.234.567"])


class GermanRunTest(unittest.TestCase):
    """Ein Lauf mit 1.500 erzeugten Zeilen; alle Ausgaben werden gelesen."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        tmp = Path(cls._tmp.name)
        rows_a, rows_b, _ = generate.build(1500, 3)
        generate.write_files(tmp / "in", rows_a, rows_b)
        cls.out = tmp / "out"
        cls.config = str(ROOT / "config.example.toml")
        cls.argv = ["run", "--input", str(tmp / "in" / "*.csv"), "--out", str(cls.out), "--config", cls.config]
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            cls.code = cli.main(cls.argv)
        cls.stdout, cls.stderr = stdout.getvalue(), stderr.getvalue()
        cls.result = run([str(tmp / "in" / "*.csv")], load_config(cls.config), tmp / "out2")
        cls.page = (cls.out / "review.html").read_text(encoding="utf-8")
        cls.report = (cls.out / "report.md").read_text(encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    # -- Konsole
    def test_console_output_is_german_and_aligned(self):
        self.assertEqual(self.code, 0)
        lines = self.stdout.splitlines()
        labels = ["Eingangszeilen", "Ausgeschlossen", "Zusammengeführt", "Saubere Kontakte", "  davon verdächtig"]
        r = self.result
        counts = [r.n_input, r.n_excluded, r.n_absorbed, r.n_output, r.n_suspect]
        for line, label, n in zip(lines, labels, counts):
            self.assertTrue(line.startswith(label), line)
            self.assertEqual(line[20:26].strip(), format_int(n), line)   # right-aligned number column
        self.assertEqual(lines[0][20:26].strip(), "1.500")
        self.assertIn("excluded.csv", lines[1])
        self.assertIn("clean.csv", lines[3])
        self.assertIn("prüfen in", lines[4])
        self.assertEqual(lines[-1], SCHLUSSZEILE)

    def test_error_messages_are_german(self):
        stderr = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(stderr):
            code = cli.main(["run", "--input", "x.csv", "--config", str(self.out / "gibt-es-nicht.toml")])
        self.assertEqual(code, 2)
        self.assertRegex(stderr.getvalue(), r"^Fehler: Konfigurationsdatei nicht gefunden")

        stderr = io.StringIO()
        with mock.patch.object(cli, "run", side_effect=IntegrityError("Bilanz verletzt")), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(stderr):
            code = cli.main(self.argv)
        self.assertEqual(code, 1)
        self.assertIn("PRÜFUNG FEHLGESCHLAGEN: Bilanz verletzt", stderr.getvalue())
        self.assertIn("dürfen nicht importiert werden", stderr.getvalue())

    # -- Begründungen in den CSV-Dateien
    def test_reasons_in_csv_files_are_german(self):
        with (self.out / "excluded.csv").open(encoding="utf-8", newline="") as fh:
            reasons = {part.split(" (")[0] for row in csv.DictReader(fh) for part in row["reason"].split("; ")}
        self.assertLessEqual(reasons, {"interne Adresse", "Testeintrag", "Tastatur-Müll", "kein nutzbarer Kontaktweg"})
        self.assertGreaterEqual(len(reasons), 3)
        with (self.out / "clean.csv").open(encoding="utf-8", newline="") as fh:
            rows = list(csv.DictReader(fh))
        flagged = " ".join(row["suspect_reasons"] for row in rows)
        self.assertRegex(flagged, r"Name mit wenigen Vokalen \(\d+ %\)")
        self.assertIn("Ziffern im Namen", flagged)
        self.assertNotRegex(flagged, r"(?i)\b(name has|digits in|looks random|identical)\b")
        notes = " ".join(row["notes"] for row in rows)
        self.assertRegex(notes, r"unbrauchbare E-Mail|unbrauchbare Telefonnummer|nicht lesbares Datum")
        self.assertNotRegex(notes, r"unusable|unparseable|also recorded")

    # -- review.html
    def test_review_page_is_german(self):
        page = self.page
        self.assertIn('<html lang="de">', page)
        self.assertIn("<title>Prüfung vor dem Import</title>", page)
        for text in ["Freigabe", "Ausgeschlossene Zeilen", "Verdächtige Datensätze", "Größte Zusammenführungsgruppen",
                     "Eingangszeilen", "Saubere Kontakte", "Verdächtig markiert", "Alle Tabellen dieser Seite filtern",
                     "Interne Adressen", "Testeinträge", "Tastatur-Müll", "Kein Kontaktweg",
                     "<th>E-Mail</th>", "<th>Telefon</th>", "<th>Grund</th>", "<th>Warum markiert</th>",
                     ">führt<", "zusammengeführt"]:
            self.assertIn(text, page)
        for text in ["Review before import", "Sign-off", "Excluded rows", "Suspect records", "Input rows", "Largest merge",
                     "Search name", "<th>Phone</th>", "<th>Reason</th>", ">leads<", ">merged<", 'lang="en"']:
            self.assertNotIn(text, page)
        self.assertIn('data-reason="internal"', page)          # codes stay as they are

    def test_numbers_use_a_dot_as_thousands_separator(self):
        self.assertIn(">1.500<", self.page)
        self.assertNotIn("1,500", self.page)
        self.assertNotRegex(self.page, r"\b\d{1,3},\d{3}\b")

    # -- report.md
    def test_report_is_german(self):
        report = self.report
        for text in ["# Bereinigungsbericht", "## Bilanz", "## Eingabedateien", "## Ausgeschlossene Zeilen nach Grund",
                     "## Verdächtige Datensätze", "## Dubletten", "## Unbrauchbare Werte", "## Prüfungen (alle bestanden)",
                     "| Eingangszeilen | 1.500 |"]:
            self.assertIn(text, report)
        for text in ["# Cleanup report", "## Balance", "Input rows", "## Duplicates", "Integrity checks"]:
            self.assertNotIn(text, report)
        r = self.result
        self.assertIn(f"Probe: {format_int(r.n_input)} = {format_int(r.n_excluded)} + {format_int(r.n_absorbed)} + {format_int(r.n_output)}.", report)


if __name__ == "__main__":
    unittest.main()
