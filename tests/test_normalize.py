import unittest

from crm_cleanup.normalize import (clean_text, iso_date, normalize_email,
                                   normalize_name, normalize_phone)


class CleanTextTest(unittest.TestCase):
    def test_collapses_all_whitespace_including_nbsp(self):
        self.assertEqual(clean_text("  Anna   \t Müller\n"), "Anna Müller")

    def test_none_and_zero_width(self):
        self.assertEqual(clean_text(None), "")
        self.assertEqual(clean_text("a​b"), "ab")


class EmailTest(unittest.TestCase):
    def test_lowercases_and_trims(self):
        self.assertEqual(normalize_email("  Anna.Müller@Example.COM "), "")  # ü is not allowed in the local part
        self.assertEqual(normalize_email("  Anna.Mueller@Example.COM "), "anna.mueller@example.com")
        self.assertEqual(normalize_email("<mailto:a@example.com>"), "a@example.com")

    def test_internationalised_domain_is_valid(self):
        self.assertEqual(normalize_email("info@gebäude-service.de"), "info@gebäude-service.de")

    def test_display_name_form_gives_the_bare_address(self):  # item 4
        self.assertEqual(normalize_email("John Doe <john@example.com>"), "john@example.com")
        self.assertEqual(normalize_email('"Doe, John" <John@Example.com>'), "john@example.com")
        self.assertEqual(normalize_email("Doe <>"), "")

    def test_punycode_domains_are_valid(self):  # item 6
        self.assertEqual(normalize_email("anna@xn--gebude-0ra.de"), "anna@xn--gebude-0ra.de")
        self.assertEqual(normalize_email("info@example.xn--p1ai"), "info@example.xn--p1ai")
        self.assertEqual(normalize_email("a@xn--.de"), "")

    def test_invalid_values(self):
        for bad in ["", "n/a", "none", "anna.example.com", "a@@example.com", "a@example", "a b@example.com",
                    ".a@example.com", "a..b@example.com", "a@example.c", "a@-example.com", "kein mail"]:
            with self.subTest(bad=bad):
                self.assertEqual(normalize_email(bad), "")


class PhoneTest(unittest.TestCase):
    def test_many_notations_give_one_number(self):
        for raw in ["0151 0000 1234", "0151/00001234", "0151-0000-1234", "+49 151 0000 1234",
                    "+49 (0)151 0000 1234", "0049 151 00001234", "(0151) 0000 1234", "Tel. 0151 0000 1234",
                    "4915100001234", "+49 0151 00001234", "  +49151 00001234  "]:
            with self.subTest(raw=raw):
                self.assertEqual(normalize_phone(raw), "+4915100001234")

    def test_trunk_zero_after_the_country_code_is_dropped_in_every_branch(self):  # item 1
        for raw in ["0049 0151 00001234", "+49 0151 00001234", "49 0151 0000 1234", "0049 (0)151 00001234"]:
            with self.subTest(raw=raw):
                self.assertEqual(normalize_phone(raw), "+4915100001234")

    def test_zero_in_front_of_the_country_code_does_not_double_it(self):  # item 2
        for raw in ["049 151 00001234", "(049) 151 0000 1234", "049/151/00001234"]:
            with self.subTest(raw=raw):
                self.assertEqual(normalize_phone(raw), "+4915100001234")

    def test_area_code_starting_with_49_is_still_national(self):  # the reason item 2 needs a separator
        self.assertEqual(normalize_phone("04921 123456"), "+494921123456")  # Emden

    def test_bare_country_code_numbers_from_ten_digits(self):  # item 5
        self.assertEqual(normalize_phone("49 30 123456"), "+4930123456")
        self.assertEqual(normalize_phone("4930123456"), "+4930123456")
        self.assertEqual(normalize_phone("49301234"), "")        # 8 digits: too short to be sure

    def test_other_country_keeps_its_code(self):
        self.assertEqual(normalize_phone("+43 664 000 1234"), "+436640001234")
        self.assertEqual(normalize_phone("0043 664 0001234"), "+436640001234")

    def test_default_country_is_configurable(self):
        self.assertEqual(normalize_phone("0664 0001234", country_code="43"), "+436640001234")

    def test_length_limits(self):
        self.assertEqual(normalize_phone("+12345678"), "")          # 8 digits
        self.assertEqual(normalize_phone("+123456789"), "+123456789")   # 9 digits
        self.assertEqual(normalize_phone("+123456789012345"), "+123456789012345")  # 15 digits
        self.assertEqual(normalize_phone("+1234567890123456"), "")  # 16 digits

    def test_invalid_values_are_rejected_not_guessed(self):
        for bad in ["", "n/a", "keine", "12345", "0151", "+49", "tel folgt", "0151 0000 1234 ext 5",
                    "+0151 0000 1234", "15100001234", "0151 0000 1234 / 0171 999 99 99 oder 5"]:
            with self.subTest(bad=bad):
                self.assertEqual(normalize_phone(bad), "")


class NameAndDateTest(unittest.TestCase):
    def test_case_fixed_only_for_all_upper_or_all_lower(self):
        self.assertEqual(normalize_name("ANNA  MÜLLER "), "Anna Müller")
        self.assertEqual(normalize_name("anna müller"), "Anna Müller")
        self.assertEqual(normalize_name("VON DER HEIDE"), "Von der Heide")
        self.assertEqual(normalize_name("Anna McDonald"), "Anna McDonald")  # mixed case: untouched

    def test_dates(self):
        self.assertEqual(iso_date("2024-03-17"), "2024-03-17")
        self.assertEqual(iso_date("17.03.2024"), "2024-03-17")
        self.assertEqual(iso_date("17.03.2024 14:30"), "2024-03-17")
        self.assertEqual(iso_date("31.02.2024"), "")
        self.assertEqual(iso_date("n/a"), "")


if __name__ == "__main__":
    unittest.main()
