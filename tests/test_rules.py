import unittest

from crm_cleanup.rules import exclusion_reasons, suspect_flags

from .helpers import make_config, make_record


def codes(pairs):
    return [code for code, _ in pairs]


class ExclusionTest(unittest.TestCase):
    cfg = make_config()

    def test_ordinary_contact_is_kept(self):
        rec = make_record(emails=["anna.mueller@example.com"], phones=["+4915100001234"])
        self.assertEqual(exclusion_reasons(rec, self.cfg), [])

    def test_internal_domain_including_subdomains_and_address_list(self):
        for address in ["kim@example.org", "kim@team.example.org", "support@example.com"]:
            with self.subTest(address=address):
                self.assertEqual(codes(exclusion_reasons(make_record(emails=[address]), self.cfg)), ["internal"])
        self.assertEqual(exclusion_reasons(make_record(emails=["kim@notexample.org"]), self.cfg), [])

    def test_test_entries(self):
        for name, mail in [("Test Test", "x@example.com"), ("Max Mustermann", "x@example.com"), ("Anna Meier", None)]:
            rec = make_record(name=name, emails=[mail] if mail else [], phones=["+4915100001234"])
            expected = [] if name == "Anna Meier" else ["test_entry"]
            with self.subTest(name=name):
                self.assertEqual(codes(exclusion_reasons(rec, self.cfg)), expected)

    def test_keyboard_mash_by_vowel_share(self):
        rec = make_record(name="Xkjhsd Qwrtpl", emails=["x@example.com"])
        self.assertEqual(codes(exclusion_reasons(rec, self.cfg)), ["keyboard_mash"])

    def test_borderline_name_stays_and_is_flagged(self):
        rec = make_record(name="Bertschlk Kranz", emails=["x@example.com"])
        self.assertEqual(exclusion_reasons(rec, self.cfg), [])
        self.assertIn("low_vowel_share", codes(suspect_flags(rec)))

    def test_common_consonant_heavy_names_are_not_touched(self):
        for name in ["Anna Schmidt", "Ben Brandt", "L. Brandt", "Jan Strnad"]:
            rec = make_record(name=name, emails=["x@example.com"])
            with self.subTest(name=name):
                self.assertEqual(exclusion_reasons(rec, self.cfg), [])
                self.assertEqual(suspect_flags(rec), [])

    def test_no_contact_method(self):
        self.assertEqual(codes(exclusion_reasons(make_record(), self.cfg)), ["no_contact"])

    def test_priority_order_and_all_reasons_are_reported(self):
        rec = make_record(name="Test Test")  # test entry and no contact
        self.assertEqual(codes(exclusion_reasons(rec, self.cfg)), ["test_entry", "no_contact"])


class SuspectTest(unittest.TestCase):
    def flags(self, **kw):
        kw.setdefault("emails", ["anna.mueller@example.com"])
        return codes(suspect_flags(make_record(**kw)))

    def test_clean_record_has_no_flags(self):
        self.assertEqual(self.flags(phones=["+4915100001234"]), [])

    def test_name_signals(self):
        self.assertIn("digits_in_name", self.flags(name="Anna Müller 2"))
        self.assertIn("repeated_name", self.flags(name="Lena Lena"))
        self.assertIn("no_name", self.flags(name=""))
        self.assertIn("keyboard_pattern", self.flags(name="Asdfg Qwert"))

    def test_cryptic_mail_and_odd_phone(self):
        self.assertIn("cryptic_email", self.flags(emails=["xkcvbnmqz@example.com"]))
        self.assertIn("odd_phone", self.flags(phones=["+4915100000000"]))       # eight zeros in a row
        self.assertIn("odd_phone", self.flags(phones=["+491234567890"]))        # sequential
        self.assertNotIn("odd_phone", self.flags(phones=["+4915100000001"]))    # seven zeros: still ordinary
        self.assertNotIn("cryptic_email", self.flags(emails=["schmidt@example.com"]))


if __name__ == "__main__":
    unittest.main()
