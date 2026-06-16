from unittest import TestCase
from unittest.mock import patch

import frappe

from crm_lead_dedupe.leads.dup_utils import (
    DUPLICATE_THRESHOLD,
    has_working_assignment,
    is_duplicate_match,
    is_valid_auto_merge_mobile,
    norm_mobile,
    select_primary_row,
    score_duplicate,
    duplicate_filters,
)


def lead(**values):
    defaults = {
        "mobile_no": "+91 98765 43210",
        "sr_mobile_norm": "9876543210",
        "lead_name": "Patient One",
        "sr_lead_pipeline": "Main Pipeline",
        "status": "Fresh",
        "sr_lead_platform": None,
        "source": None,
    }
    defaults.update(values)
    return frappe._dict(defaults)


class TestDupUtils(TestCase):
    def test_norm_mobile_uses_last_ten_digits(self):
        self.assertEqual(norm_mobile("+91 98765 43210"), "9876543210")
        self.assertEqual(norm_mobile("43210"), "43210")
        self.assertEqual(norm_mobile(None), "")

    def test_auto_merge_mobile_requires_safe_ten_digit_key(self):
        self.assertTrue(is_valid_auto_merge_mobile("9876543210"))
        self.assertFalse(is_valid_auto_merge_mobile("43210"))
        self.assertFalse(is_valid_auto_merge_mobile("0000000000"))
        self.assertFalse(is_valid_auto_merge_mobile("9999999999"))

    def test_same_mobile_only_is_duplicate(self):
        score = score_duplicate(
            lead(lead_name="Patient One", sr_lead_pipeline="Pipeline A", status="Fresh"),
            lead(lead_name="Different Person", sr_lead_pipeline="Pipeline B", status="Closed"),
        )

        self.assertGreaterEqual(score, DUPLICATE_THRESHOLD)

    def test_same_mobile_is_duplicate_across_name_pipeline_status_and_source(self):
        score = score_duplicate(
            lead(
                lead_name="Patient One",
                sr_lead_pipeline="Pipeline A",
                status="Fresh",
                source="Website",
                sr_lead_platform="Meta",
            ),
            lead(
                lead_name="Different Person",
                sr_lead_pipeline="Pipeline B",
                status="Fresh",
                source="Website",
                sr_lead_platform="Meta",
            ),
        )

        self.assertEqual(score, 100)

    def test_same_mobile_and_pipeline_is_duplicate(self):
        candidate = lead(lead_name="Different Person", sr_lead_pipeline="Main Pipeline")

        self.assertTrue(is_duplicate_match(lead(), candidate))

    def test_same_mobile_and_name_is_duplicate_without_pipeline_match(self):
        candidate = lead(sr_lead_pipeline="Different Pipeline")

        self.assertTrue(is_duplicate_match(lead(), candidate))

    def test_different_mobile_is_not_duplicate(self):
        candidate = lead(mobile_no="+91 11111 22222", sr_mobile_norm="1111122222")

        self.assertEqual(score_duplicate(lead(), candidate), 0)

    def test_active_assigned_working_lead_wins(self):
        rows = [
            lead(name="NEW-AGENT-2", creation="2026-05-21 10:00:00", lead_owner="agent2@example.com"),
            lead(name="OLD-AGENT-1", creation="2026-05-20 10:00:00", lead_owner="agent1@example.com"),
        ]

        self.assertEqual(select_primary_row(rows).name, "OLD-AGENT-1")

    def test_newest_active_lead_wins_when_no_active_assigned_lead_exists(self):
        rows = [
            lead(name="NEW-ACTIVE", creation="2026-05-21 10:00:00"),
            lead(name="OLD-ACTIVE", creation="2026-05-20 10:00:00"),
        ]

        self.assertEqual(select_primary_row(rows).name, "NEW-ACTIVE")

    def test_converted_and_archived_leads_do_not_win_over_active_leads(self):
        rows = [
            lead(name="NEW-CONVERTED", creation="2026-05-21 10:00:00", converted=1),
            lead(name="MID-ARCHIVED", creation="2026-05-20 10:00:00", sr_is_archived=1),
            lead(name="OLD-ACTIVE", creation="2026-05-19 10:00:00"),
        ]

        self.assertEqual(select_primary_row(rows).name, "OLD-ACTIVE")

    def test_newest_primary_setting_makes_newest_active_lead_win(self):
        rows = [
            lead(name="NEW-AGENT-2", creation="2026-05-21 10:00:00", lead_owner="agent2@example.com"),
            lead(name="OLD-AGENT-1", creation="2026-05-20 10:00:00", lead_owner="agent1@example.com"),
        ]

        with patch("crm_lead_dedupe.leads.dup_utils.get_setting", return_value=1):
            self.assertEqual(select_primary_row(rows).name, "NEW-AGENT-2")

    def test_pipeline_scope_adds_pipeline_to_duplicate_filters_when_enabled(self):
        with (
            patch("crm_lead_dedupe.leads.dup_utils.get_setting", return_value=1),
            patch("frappe.db.has_column", return_value=True),
        ):
            self.assertEqual(
                duplicate_filters("9876543210", "Skin"),
                {"sr_mobile_norm": "9876543210", "sr_lead_pipeline": "Skin"},
            )

    def test_pipeline_scope_is_disabled_by_default(self):
        with patch("crm_lead_dedupe.leads.dup_utils.get_setting", return_value=0):
            self.assertEqual(duplicate_filters("9876543210", "Skin"), {"sr_mobile_norm": "9876543210"})

    def test_assign_json_counts_as_working_assignment(self):
        self.assertTrue(has_working_assignment(lead(_assign='["agent@example.com"]')))
