import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe

from crm_lead_dedupe import hooks, logging, privacy
from crm_lead_dedupe.api import crm_lead_duplicates


class TestDedupeNumberPrivacy(unittest.TestCase):
    phone = "9876501234"

    def test_project_masks_modal_fields_and_errors_without_mutation(self):
        raw = {
            "name": "CRM-LEAD-1",
            "mobile_no": self.phone,
            "phone": self.phone,
            "lead_name": f"Caller {self.phone}",
            "error": f"Merge failed for {self.phone}",
            "provider_response": {"phoneNumber": self.phone},
        }

        result = privacy.project(raw)

        self.assertNotIn(self.phone, frappe.as_json(result))
        self.assertNotIn("provider_response", result)
        self.assertEqual(raw["mobile_no"], self.phone)

    def test_duplicate_modal_projects_restricted_rows(self):
        lead = frappe._dict(
            name="CRM-LEAD-1",
            mobile_no=self.phone,
            sr_lead_pipeline="Pipeline",
        )
        raw_summary = {
            "name": "CRM-LEAD-2",
            "mobile_no": self.phone,
            "phone": self.phone,
            "lead_name": f"Caller {self.phone}",
        }
        with patch.object(crm_lead_duplicates, "is_enabled", return_value=True),              patch.object(crm_lead_duplicates, "require_lead_read"),              patch.object(crm_lead_duplicates.frappe, "get_doc", return_value=lead),              patch.object(
                 crm_lead_duplicates,
                 "find_dup_candidates",
                 return_value=[{"name": "CRM-LEAD-2"}],
             ),              patch.object(crm_lead_duplicates, "score_duplicate", return_value=100),              patch.object(crm_lead_duplicates, "can_manage_dedupe", return_value=True),              patch.object(
                 crm_lead_duplicates,
                 "get_effective_modal_columns",
                 return_value=["name", "mobile_no", "phone", "lead_name"],
             ),              patch.object(crm_lead_duplicates, "_summary", return_value=raw_summary),              patch.object(privacy, "restricted", return_value=True):
            result = crm_lead_duplicates.get_duplicates_for_crm_lead("CRM-LEAD-1")

        self.assertNotIn(self.phone, frappe.as_json(result))
        self.assertEqual(raw_summary["mobile_no"], self.phone)

    def test_full_visibility_preserves_custom_api_response(self):
        raw = {"mobile_no": self.phone}
        endpoint = privacy.browser_response(lambda: raw)

        with patch.object(privacy, "restricted", return_value=False):
            self.assertIs(endpoint(), raw)

    def test_sensitive_admin_doctypes_require_full_visibility(self):
        for doctype in privacy.SENSITIVE_DOCTYPES:
            with self.subTest(doctype=doctype),                  patch.object(privacy, "restricted", return_value=True):
                with self.assertRaises(frappe.PermissionError):
                    privacy.check_sensitive_doctype(doctype)
                self.assertEqual(privacy.query_condition(), "1=0")

            with patch.object(privacy, "restricted", return_value=False):
                privacy.check_sensitive_doctype(doctype)
                self.assertEqual(privacy.query_condition(), "")

    def test_raw_mobile_action_requires_full_visibility(self):
        with patch.object(privacy, "restricted", return_value=True):
            with self.assertRaises(frappe.PermissionError):
                privacy.require_full_number_visibility()

    def test_operational_logger_masks_numbers(self):
        logger = MagicMock()
        with patch.object(logging.frappe, "logger", return_value=logger),              patch.object(logging, "get_setting", return_value=False):
            logging.log_operation(
                "dedupe.test",
                mobile_norm=self.phone,
                error=f"Failed for {self.phone}",
            )

        message = logger.info.call_args.args[0]
        self.assertNotIn(self.phone, message)
        self.assertIn("******1234", message)

    def test_privacy_hooks_cover_raw_admin_doctypes(self):
        for doctype in privacy.SENSITIVE_DOCTYPES:
            self.assertEqual(
                hooks.has_permission[doctype],
                "crm_lead_dedupe.privacy.has_permission",
            )
            self.assertEqual(
                hooks.permission_query_conditions[doctype],
                "crm_lead_dedupe.privacy.query_condition",
            )

    def test_before_request_defers_token_identity_to_auth_hook(self):
        request = SimpleNamespace(
            path="/api/resource/CRM%20Lead%20Auto%20Merge%20Log",
            headers={"Authorization": "token key:secret"},
        )
        with (
            patch.object(privacy.frappe.local, "request", request, create=True),
            patch.object(privacy.frappe, "session", SimpleNamespace(user="Guest")),
            patch.object(privacy, "check_sensitive_doctype") as check,
        ):
            privacy.guard_request()

        check.assert_not_called()
