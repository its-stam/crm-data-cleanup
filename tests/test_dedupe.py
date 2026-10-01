import unittest

from crm_cleanup.dedupe import UnionFind, group_records, merge_group

from .helpers import make_record

M1, M2, M3 = "a@example.com", "b@example.com", "c@example.com"
T1, T2, T3 = "+4915100000001", "+4915100000002", "+4915100000003"


class UnionFindTest(unittest.TestCase):
    def test_transitive_and_smaller_index_is_root(self):
        uf = UnionFind(5)
        uf.union(3, 1)
        uf.union(3, 4)
        self.assertEqual({uf.find(i) for i in (1, 3, 4)}, {1})
        self.assertNotEqual(uf.find(0), uf.find(1))


class GroupingTest(unittest.TestCase):
    def test_chain_through_mail_then_phone_is_one_group(self):
        # A-B share an e-mail, B-C share a phone number; A and C share nothing.
        a = make_record(0, emails=[M1], phones=[T1])
        b = make_record(1, emails=[M1], phones=[T2])
        c = make_record(2, emails=[M2], phones=[T2])
        d = make_record(3, emails=[M3], phones=[T3])
        self.assertFalse(set(a.emails) & set(c.emails) or set(a.phones) & set(c.phones))
        groups = group_records([a, b, c, d])
        self.assertEqual([[r.index for r in g] for g in groups], [[0, 1, 2], [3]])

    def test_chain_in_reverse_order_and_second_mail(self):
        c = make_record(0, emails=[M2], phones=[T2])
        b = make_record(1, emails=[M1, M2], phones=[])
        a = make_record(2, emails=[M1], phones=[T1])
        self.assertEqual(len(group_records([c, b, a])), 1)

    def test_rows_without_shared_keys_stay_apart(self):
        rows = [make_record(i, emails=[f"x{i}@example.com"], phones=[f"+49151000000{i}"]) for i in range(4)]
        self.assertEqual(len(group_records(rows)), 4)


class MergeTest(unittest.TestCase):
    def test_most_complete_row_leads_and_extras_go_to_second_slots(self):
        sparse = make_record(0, uid="a:1", emails=[M1], phones=[])
        rich = make_record(1, uid="b:1", emails=[M1, M2], phones=[T1, T2], company="Acme", city="Ulm",
                           created="2022-05-01")
        third = make_record(2, uid="a:2", emails=[M3], phones=[T1], created="2021-01-01")
        contact = merge_group([sparse, rich, third])
        self.assertEqual(contact.id, "b:1")
        self.assertEqual(contact.merged_from, ["a:2", "a:1"])   # most complete first
        self.assertEqual(contact.emails, [M1, M2, M3])      # leader's first, nothing lost
        self.assertEqual(contact.phones, [T1, T2])
        self.assertEqual((contact.company, contact.city), ("Acme", "Ulm"))
        self.assertEqual(contact.created, "2021-01-01")     # earliest

    def test_ties_go_to_the_earlier_row(self):
        first = make_record(0, uid="a:1", emails=[M1])
        second = make_record(1, uid="a:2", emails=[M1])
        self.assertEqual(merge_group([second, first]).id, "a:1")

    def test_empty_fields_are_filled_from_other_rows(self):
        lead = make_record(0, emails=[M1], phones=[T1], company="", city="Ulm")
        other = make_record(1, emails=[M1], company="Acme", city="")
        contact = merge_group([lead, other])
        self.assertEqual((contact.company, contact.city), ("Acme", "Ulm"))

    def test_abbreviated_name_is_replaced_and_variants_are_noted(self):
        lead = make_record(0, name="L. Brandt", emails=[M1], phones=[T1], company="Acme")
        other = make_record(1, name="Leon Brandt", emails=[M1])
        contact = merge_group([lead, other])
        self.assertEqual(contact.id, lead.uid)
        self.assertEqual(contact.name, "Leon Brandt")
        self.assertIn("auch erfasst als: L. Brandt", contact.notes)

    def test_unusable_values_are_kept_in_the_notes(self):
        row = make_record(0, emails=[M1], unusable=["unbrauchbare Telefonnummer 'n/a'"])
        self.assertEqual(merge_group([row]).notes, [f"unbrauchbare Telefonnummer 'n/a' ({row.uid})"])


if __name__ == "__main__":
    unittest.main()
