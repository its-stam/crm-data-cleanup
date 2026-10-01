import contextlib
import copy
import io
import re
import tempfile
import unittest
from pathlib import Path

from crm_cleanup import cli, generate
from crm_cleanup.checks import Expected, IntegrityError, check_balance, verify
from crm_cleanup.config import ConfigError, load_config
from crm_cleanup.normalize import normalize_phone
from crm_cleanup.pipeline import process, run

from .helpers import ROOT, write_rows

HEAD_A = ["Contact ID", "Full Name", "Email", "Phone", "Company", "City", "Created"]
HEAD_B = ["Kontakt-Nr", "Vorname", "Nachname", "E-Mail", "Telefon", "Mobil", "Firma", "Ort", "Erstellt am"]


def mini_dataset(folder: Path):
    """Small hand-made input: one chain A1-B1-A3, one bridge-through-an-excluded-row case, junk."""
    a = write_rows(folder / "crm_export_a.csv", HEAD_A, [
        ["A1", "Anna Müller", "ANNA@example.com", "0151 0000 0001", "Acme", "Ulm", "2024-03-17"],   # chain start
        ["A2", "Test Person", "shared@example.com", "0151 0000 0099", "", "", ""],                   # excluded: test
        ["A3", "A. Müller", "anna.m@example.com", "", "", "", ""],                                   # chain end
        ["A4", "Kim Real", "", "+49 151 0000 0099", "", "", ""],                                     # shares phone with A2
        ["A5", "Lee Real", "shared@example.com", "", "", "", ""],                                    # shares mail with A2
        ["A6", "Pat Intern", "pat@example.org", "0151 0000 0005", "", "", ""],                       # excluded: internal
        ["A7", "Xkjhsd Qwrtpl", "x@example.com", "", "", "", ""],                                    # excluded: mash
        ["A8", "Nobody", "n/a", "12345", "", "", ""],                                                # excluded: no contact
        ["A9", "<script>alert(1)</script> Kim", "kim@example.com", "", "", "", ""],
    ])
    b = write_rows(folder / "crm_export_b.csv", HEAD_B, [
        ["B1", "Anna", "Müller", "anna.m@example.com", "+49 (0)151 0000 0001", "", "", "", "17.03.2024"],  # links A1 and A3
    ])
    return [a, b]


class PipelineTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.cfg = load_config(ROOT / "config.example.toml")
        self.paths = mini_dataset(self.tmp)

    def tearDown(self):
        self._tmp.cleanup()

    def test_balance_and_groups(self):
        r = process(self.paths, self.cfg)
        self.assertEqual((r.n_input, r.n_excluded, r.n_absorbed, r.n_output), (10, 4, 2, 4))
        self.assertEqual(r.n_input, r.n_excluded + r.n_absorbed + r.n_output)
        reasons = sorted(row["reason_code"] for row in r.excluded_rows)
        self.assertEqual(reasons, ["internal", "keyboard_mash", "no_contact", "test_entry"])

    def test_chain_is_one_contact_and_excluded_rows_do_not_bridge(self):
        r = process(self.paths, self.cfg)
        by_id = {row["id"]: row for row in r.clean_rows}
        chain = next(row for row in r.clean_rows if "crm_export_b:B1" in row["merged_from"])
        self.assertEqual(sorted([chain["email"], chain["email_2"]]), ["anna.m@example.com", "anna@example.com"])
        self.assertEqual(chain["phone"], "+4915100000001")
        self.assertEqual(chain["name"], "Anna Müller")
        self.assertEqual(chain["created"], "2024-03-17")
        # A4 and A5 both touch the excluded test row A2, but through different keys: they stay two contacts.
        self.assertIn("crm_export_a:A4", by_id)
        self.assertIn("crm_export_a:A5", by_id)
        self.assertEqual(by_id["crm_export_a:A4"]["merged_from"], "")

    def test_nothing_is_deleted_excluded_rows_keep_their_values(self):
        r = process(self.paths, self.cfg)
        row = next(x for x in r.excluded_rows if x["id"] == "crm_export_a:A8")
        self.assertEqual((row["email"], row["phone"]), ("n/a", "12345"))
        self.assertEqual(row["reason_code"], "no_contact")

    def test_run_writes_four_files_and_review_page_escapes_html(self):
        out = self.tmp / "out"
        run([str(p) for p in self.paths], self.cfg, out)
        self.assertEqual(sorted(p.name for p in out.iterdir()), ["clean.csv", "excluded.csv", "report.md", "review.html"])
        page = (out / "review.html").read_text(encoding="utf-8")
        self.assertNotIn("<script>alert(1)", page)
        self.assertIn("test_entry", page)

    def test_wildcards_and_argument_order_do_not_change_the_result(self):
        r1 = process(sorted(self.paths), self.cfg)
        out1, out2 = self.tmp / "o1", self.tmp / "o2"
        run([str(self.tmp / "crm_export_*.csv")], self.cfg, out1)
        run([str(self.paths[1]), str(self.paths[0])], self.cfg, out2)
        self.assertEqual((out1 / "clean.csv").read_bytes(), (out2 / "clean.csv").read_bytes())
        self.assertEqual(len(r1.clean_rows), len((out1 / "clean.csv").read_text(encoding="utf-8").splitlines()) - 1)

    def test_unknown_file_and_missing_column_are_clear_errors(self):
        other = write_rows(self.tmp / "other.csv", ["x"], [["1"]])
        with self.assertRaises(ConfigError):
            process([other], self.cfg)
        broken = write_rows(self.tmp / "crm_export_a2.csv", ["Contact ID", "Full Name"], [["1", "x"]])
        with self.assertRaisesRegex(ConfigError, "not in the file"):
            process([broken], self.cfg)

    def test_duplicate_ids_in_one_file_get_distinct_uids(self):
        dup = write_rows(self.tmp / "crm_export_a3.csv", HEAD_A, [
            ["1", "Anna Müller", "a1@example.com", "", "", "", ""], ["1", "Ben Meier", "b1@example.com", "", "", "", ""]])
        r = process([dup], self.cfg)
        self.assertEqual(len({c["id"] for c in r.clean_rows}), 2)
        self.assertTrue(r.warnings)


class IntegrityTest(unittest.TestCase):
    """The checks must fail when the numbers or the data are manipulated."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.cfg = load_config(ROOT / "config.example.toml")
        self.result = process(mini_dataset(Path(self._tmp.name)), self.cfg)
        self.expected = Expected.from_records(self.result.records)
        self.clean = copy.deepcopy(self.result.clean_rows)
        self.excluded = copy.deepcopy(self.result.excluded_rows)

    def tearDown(self):
        self._tmp.cleanup()

    def test_untouched_result_passes(self):
        verify(self.expected, self.clean, self.excluded)

    def test_manipulated_count_fails_the_balance(self):
        check_balance(10, 4, 2, 4)
        with self.assertRaisesRegex(IntegrityError, "balance broken"):
            check_balance(10, 4, 2, 5)
        with self.assertRaisesRegex(IntegrityError, "balance broken"):
            check_balance(10, 4, 2, 3)

    def test_a_dropped_output_row_fails(self):
        with self.assertRaisesRegex(IntegrityError, "balance broken"):
            verify(self.expected, self.clean[:-1], self.excluded)

    def test_an_excluded_row_moved_back_into_the_count_fails(self):
        with self.assertRaises(IntegrityError):
            verify(self.expected, self.clean, self.excluded[:-1])

    def test_a_lost_email_fails(self):
        target = next(row for row in self.clean if row["email_2"])
        target["email_2"] = ""
        with self.assertRaisesRegex(IntegrityError, "lost contact data"):
            verify(self.expected, self.clean, self.excluded)

    def test_a_duplicated_key_fails(self):
        self.clean[0]["email_2"] = self.clean[1]["email"] or "same@example.com"
        self.clean[1]["email"] = self.clean[1]["email"] or "same@example.com"
        with self.assertRaises(IntegrityError):
            verify(self.expected, self.clean, self.excluded)

    def test_a_trunk_zero_behind_the_country_code_fails(self):  # item 3
        row = next(row for row in self.clean if not row["phone_2"])
        row["phone_2"] = "+49015100001234"      # nothing is lost or duplicated: only the format is wrong
        with self.assertRaisesRegex(IntegrityError, "invalid phone"):
            verify(self.expected, self.clean, self.excluded)

    def test_a_badly_formatted_phone_fails(self):
        row = next(row for row in self.clean if row["phone"])
        row["phone"] = "0151 0000 0001"
        with self.assertRaises(IntegrityError):
            verify(self.expected, self.clean, self.excluded)


class GeneratorTest(unittest.TestCase):
    def test_deterministic(self):
        self.assertEqual(generate.build(400, 5), generate.build(400, 5))
        self.assertNotEqual(generate.build(400, 5)[0], generate.build(400, 6)[0])

    def test_committed_sample_files_are_the_seed_42_output(self):
        rows_a, rows_b, _ = generate.build(2000, 42)
        with tempfile.TemporaryDirectory() as tmp:
            for path in generate.write_files(tmp, rows_a, rows_b):
                self.assertEqual(path.read_bytes(), (ROOT / "data" / "sample" / path.name).read_bytes(), path.name)

    def test_only_invented_data(self):
        rows_a, rows_b, _ = generate.build(1000, 3)
        text = "\n".join(",".join(r) for r in rows_a + rows_b)
        self.assertLessEqual(set(re.findall(r"@+([\w.-]+)", text.lower())), {"example.com", "example.org", "example"})
        cells = [r[3] for r in rows_a] + [c for r in rows_b for c in r[4:6]]
        for cell in filter(None, cells):
            if cell in generate.BAD_PHONE:
                continue
            self.assertRegex(normalize_phone(cell), r"^\+491510000\d{4}$", cell)

    def test_pipeline_result_matches_the_ground_truth(self):
        rows_a, rows_b, truth = generate.build(800, 7)
        with tempfile.TemporaryDirectory() as tmp:
            generate.write_files(tmp, rows_a, rows_b)
            r = run([str(Path(tmp) / "*.csv")], load_config(ROOT / "config.example.toml"), Path(tmp) / "out")
        self.assertEqual(
            (r.n_input, r.n_excluded, r.n_absorbed, r.n_output),
            (truth["rows"], truth["excluded"], truth["absorbed"], truth["clean"]),
        )


class CliTest(unittest.TestCase):
    def call(self, *argv):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return cli.main(list(argv))

    def test_exit_codes(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows_a, rows_b, _ = generate.build(200, 1)
            generate.write_files(tmp, rows_a, rows_b)
            config = str(ROOT / "config.example.toml")
            base = ["run", "--input", f"{tmp}/*.csv", "--out", f"{tmp}/out"]
            self.assertEqual(self.call(*base, "--config", config), 0)
            self.assertEqual(self.call(*base, "--config", f"{tmp}/missing.toml"), 2)
            self.assertEqual(self.call("run", "--input", f"{tmp}/nothing*.csv", "--config", config), 2)


if __name__ == "__main__":
    unittest.main()
