from contextlib import nullcontext
from datetime import datetime
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe

from crm_lead_dedupe import scheduler


def lead(name, creation, owner=None):
    return frappe._dict(
        name=name,
        creation=creation,
        lead_owner=owner,
        _assign=frappe.as_json([owner]) if owner else "[]",
        status="Fresh",
    )


class TestPrimaryReassignment(TestCase):
    def _run_group(self, *, mode="oldest", complete=True, allow_merge=True, fail=False, single=False):
        older = lead("TEST-OLDER", "2026-09-23 10:00:00", "agent@example.com")
        newest = lead("TEST-NEWEST", "2026-09-23 11:00:00")
        rows = [older] if single else [newest, older]
        primary = newest if mode == "newest" else older
        remaining = [primary] if complete else rows

        def setting(key):
            return int(key == f"crm_lead_dedupe_{mode}_primary_enabled")

        fake_frappe = SimpleNamespace(
            db=MagicMock(), flags=frappe._dict(), log_error=MagicMock(),
            get_traceback=MagicMock(return_value="merge failed"),
        )
        with (
            patch.object(scheduler, "frappe", fake_frappe),
            patch.object(scheduler, "_blocked_mobiles", return_value=set()),
            patch.object(scheduler, "filelock", return_value=nullcontext()),
            patch.object(scheduler, "_group_rows", side_effect=[rows, remaining]),
            patch("crm_lead_dedupe.leads.dup_utils.get_setting", side_effect=setting),
            patch.object(scheduler, "is_merge_status_allowed", return_value=True),
            patch.object(scheduler, "_merge_duplicate", return_value=True,
                         side_effect=RuntimeError("merge failed") if fail else None),
            patch.object(scheduler, "_set_group_status"),
            patch.object(scheduler, "_write_merge_log"),
            patch.object(scheduler, "now_datetime", return_value=datetime(2026, 9, 23, 12)),
            patch.object(scheduler, "sync_duplicate_group"),
            patch.object(scheduler, "_refresh_master_creation_from_newest"),
            patch.object(scheduler, "_finalize_group_state"),
            patch.object(scheduler, "_clear_master_assignment") as clear_assignment,
        ):
            merged = scheduler.process_mobile_group(
                "9876543210", 10, 50, allow_merge=allow_merge,
            )
        if not fail:
            fake_frappe.get_traceback.assert_not_called()
        return merged, clear_assignment, fake_frappe

    def test_completed_oldest_primary_merge_clears_assignment(self):
        merged, clear_assignment, _ = self._run_group()
        self.assertEqual(merged, 1)
        clear_assignment.assert_called_once_with("TEST-OLDER")

    def test_completed_newest_primary_merge_clears_assignment(self):
        merged, clear_assignment, _ = self._run_group(mode="newest")
        self.assertEqual(merged, 1)
        clear_assignment.assert_called_once_with("TEST-NEWEST")

    def test_default_primary_mode_preserves_owner(self):
        merged, clear_assignment, fake_frappe = self._run_group(mode="default")
        self.assertEqual(merged, 1)
        clear_assignment.assert_not_called()
        self.assertEqual(fake_frappe.db.set_value.call_args.args[2]["lead_owner"], "agent@example.com")

    def test_partial_group_keeps_assignment(self):
        for mode in ("oldest", "newest"):
            with self.subTest(mode=mode):
                _, clear_assignment, _ = self._run_group(mode=mode, complete=False)
                clear_assignment.assert_not_called()

    def test_failed_merge_keeps_assignment(self):
        for mode in ("oldest", "newest"):
            with self.subTest(mode=mode):
                merged, clear_assignment, _ = self._run_group(mode=mode, fail=True, complete=False)
                self.assertEqual(merged, 0)
                clear_assignment.assert_not_called()

    def test_archive_only_keeps_assignment(self):
        for mode in ("oldest", "newest"):
            with self.subTest(mode=mode):
                merged, clear_assignment, _ = self._run_group(mode=mode, allow_merge=False)
                self.assertEqual(merged, 0)
                clear_assignment.assert_not_called()

    def test_single_lead_keeps_assignment(self):
        for mode in ("oldest", "newest"):
            with self.subTest(mode=mode):
                merged, clear_assignment, _ = self._run_group(mode=mode, single=True)
                self.assertEqual(merged, 0)
                clear_assignment.assert_not_called()


class TestClearMasterAssignment(TestCase):
    def test_uses_assignment_service_when_installed(self):
        service = MagicMock()
        fake_frappe = SimpleNamespace(
            get_installed_apps=lambda: ["new_assignement_system"], db=MagicMock(),
        )
        with (
            patch.object(scheduler, "frappe", fake_frappe),
            patch.dict("sys.modules", {"new_assignement_system.engine.service": service}),
        ):
            scheduler._clear_master_assignment("TEST-OLDER")
        service.clear_lead_assignment.assert_called_once_with(
            "TEST-OLDER",
            reason="CRM Lead retained as primary after duplicate merge",
            triggered_by="CRM Lead Dedupe",
        )
        fake_frappe.db.set_value.assert_not_called()

    def test_fallback_clears_todos_owner_and_assignments(self):
        for has_team in (True, False):
            with self.subTest(has_team=has_team):
                fake_frappe = SimpleNamespace(get_installed_apps=lambda: [], db=MagicMock())
                fake_frappe.db.has_column.return_value = has_team
                with (
                    patch.object(scheduler, "frappe", fake_frappe),
                    patch("frappe.desk.form.assign_to.clear") as clear,
                ):
                    scheduler._clear_master_assignment("TEST-OLDER")
                clear.assert_called_once_with("CRM Lead", "TEST-OLDER", ignore_permissions=True)
                values = {"lead_owner": None, "_assign": "[]"}
                if has_team:
                    values["team"] = None
                fake_frappe.db.set_value.assert_called_once_with(
                    "CRM Lead", "TEST-OLDER", values, update_modified=False,
                )
