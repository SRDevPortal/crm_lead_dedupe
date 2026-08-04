from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe

from crm_lead_dedupe.leads.dup_hooks import _mark_doc_pending
from crm_lead_dedupe.scheduler import _set_group_status


FIXED_NOW = datetime(2026, 8, 3, 12, 0, 0)


class MockLead(frappe._dict):
    def is_new(self):
        return True


def lead(**values):
    data = {
        "name": "MOCK-LEAD-1",
        "sr_mobile_norm": "9876543210",
        "sr_lead_pipeline": "Mock Pipeline",
        "source": "Mock Source",
        "sr_dedupe_pending": 0,
        "sr_dedupe_status": None,
        "sr_dedupe_stage": None,
        "sr_dedupe_result": None,
        "sr_dedupe_pipeline": None,
        "sr_dedupe_queued_at": None,
        "sr_dedupe_not_before": None,
        "sr_dedupe_started_at": None,
        "sr_dedupe_completed_at": None,
        "sr_dedupe_input_hash": None,
        "sr_dedupe_error": None,
    }
    data.update(values)
    return MockLead(data)


def setting(key):
    return {
        "crm_lead_dedupe_delay_seconds": 30,
        "crm_lead_dedupe_require_pipeline": 0,
        "crm_lead_dedupe_require_source": 0,
    }.get(key, 0)


class TestDedupeMockActions(TestCase):
    def test_action_queue_lead_with_30_second_delay(self):
        doc = lead()
        with (
            patch("crm_lead_dedupe.leads.dup_hooks.now_datetime", return_value=FIXED_NOW),
            patch("crm_lead_dedupe.leads.dup_hooks.get_setting", side_effect=setting),
        ):
            _mark_doc_pending(doc, force=True)

        self.assertEqual(doc.sr_dedupe_stage, "Pending")
        self.assertEqual(doc.sr_dedupe_queued_at, FIXED_NOW)
        self.assertEqual(doc.sr_dedupe_not_before, FIXED_NOW + timedelta(seconds=30))
        self.assertEqual(doc.sr_dedupe_pending, 1)

    def test_action_wait_for_required_pipeline(self):
        doc = lead(sr_lead_pipeline=None)

        def required_pipeline(key):
            if key == "crm_lead_dedupe_delay_seconds":
                return 30
            return 1 if key == "crm_lead_dedupe_require_pipeline" else 0

        with (
            patch("crm_lead_dedupe.leads.dup_hooks.now_datetime", return_value=FIXED_NOW),
            patch("crm_lead_dedupe.leads.dup_hooks.get_setting", side_effect=required_pipeline),
        ):
            _mark_doc_pending(doc, force=True)

        self.assertEqual(doc.sr_dedupe_stage, "Waiting for Metadata")
        self.assertEqual(doc.sr_dedupe_not_before, FIXED_NOW + timedelta(seconds=30))

    def test_action_skip_unsafe_mobile(self):
        doc = lead(sr_mobile_norm="0000000000")
        with (
            patch("crm_lead_dedupe.leads.dup_hooks.now_datetime", return_value=FIXED_NOW),
            patch("crm_lead_dedupe.leads.dup_hooks.get_setting", side_effect=setting),
        ):
            _mark_doc_pending(doc, force=True)

        self.assertEqual(doc.sr_dedupe_stage, "Completed")
        self.assertEqual(doc.sr_dedupe_result, "Skipped")
        self.assertEqual(doc.sr_dedupe_pending, 0)

    def test_action_finalize_primary_state(self):
        db = MagicMock()
        db.has_column.return_value = True
        fake_frappe = SimpleNamespace(db=db, get_all=MagicMock(return_value=["MOCK-LEAD-1"]))
        with (
            patch("crm_lead_dedupe.scheduler.frappe", fake_frappe),
            patch("crm_lead_dedupe.scheduler.duplicate_filters", return_value={}),
            patch("crm_lead_dedupe.scheduler.now_datetime", return_value=FIXED_NOW),
        ):
            _set_group_status("9876543210", None, "Master")

        values = db.bulk_update.call_args.args[1]["MOCK-LEAD-1"]
        self.assertEqual(values["sr_dedupe_stage"], "Completed")
        self.assertEqual(values["sr_dedupe_result"], "Primary")
        self.assertEqual(values["sr_dedupe_pending"], 0)

    def test_action_finalize_duplicate_state(self):
        db = MagicMock()
        db.has_column.return_value = True
        fake_frappe = SimpleNamespace(db=db, get_all=MagicMock(return_value=["MOCK-LEAD-2"]))
        with (
            patch("crm_lead_dedupe.scheduler.frappe", fake_frappe),
            patch("crm_lead_dedupe.scheduler.duplicate_filters", return_value={}),
            patch("crm_lead_dedupe.scheduler.now_datetime", return_value=FIXED_NOW),
        ):
            _set_group_status("9876543210", None, "Duplicate")

        values = db.bulk_update.call_args.args[1]["MOCK-LEAD-2"]
        self.assertEqual(values["sr_dedupe_stage"], "Completed")
        self.assertEqual(values["sr_dedupe_result"], "Duplicate")
        self.assertEqual(values["sr_dedupe_pending"], 0)
