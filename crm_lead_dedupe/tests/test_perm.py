from unittest import TestCase
from unittest.mock import patch

import frappe

from crm_lead_dedupe.leads.perm import (
    ACTIVE_LEAD_CONDITION,
    can_customize_modal_columns,
    crm_lead_has_permission,
    pqc_crm_lead,
)


class TestCRMLeadDedupePermissions(TestCase):
    def test_non_manager_query_condition_forces_active_leads(self):
        with patch("frappe.get_roles", return_value=["Agent"]):
            condition = pqc_crm_lead("agent@example.com")

        self.assertEqual(condition, ACTIVE_LEAD_CONDITION)
        self.assertIn("sr_is_archived", condition)
        self.assertIn("converted", condition)

    def test_manager_query_condition_still_forces_active_leads(self):
        with patch("frappe.get_roles", return_value=["Sales Manager"]):
            condition = pqc_crm_lead("manager@example.com")

        self.assertEqual(condition, ACTIVE_LEAD_CONDITION)

    def test_non_manager_cannot_open_archived_or_converted_leads(self):
        archived = frappe._dict(sr_is_archived=1, converted=0)
        converted = frappe._dict(sr_is_archived=0, converted=1)

        with patch("frappe.get_roles", return_value=["Agent"]):
            self.assertFalse(crm_lead_has_permission(archived, "read", "agent@example.com"))
            self.assertFalse(crm_lead_has_permission(converted, "read", "agent@example.com"))
            self.assertFalse(crm_lead_has_permission(archived, "write", "agent@example.com"))

    def test_non_manager_active_leads_fall_back_to_standard_permissions(self):
        active = frappe._dict(sr_is_archived=0, converted=0)

        with patch("frappe.get_roles", return_value=["Agent"]):
            self.assertIsNone(crm_lead_has_permission(active, "read", "agent@example.com"))

    def test_manager_direct_access_falls_back_to_standard_permissions(self):
        archived = frappe._dict(sr_is_archived=1, converted=1)

        with patch("frappe.get_roles", return_value=["CRM Manager"]):
            self.assertIsNone(crm_lead_has_permission(archived, "read", "manager@example.com"))

    def test_only_system_manager_can_customize_modal_columns(self):
        with patch("frappe.get_roles", return_value=["CRM Manager"]):
            self.assertFalse(can_customize_modal_columns("manager@example.com"))

        with patch("frappe.get_roles", return_value=["System Manager"]):
            self.assertTrue(can_customize_modal_columns("system@example.com"))

        self.assertTrue(can_customize_modal_columns("Administrator"))
