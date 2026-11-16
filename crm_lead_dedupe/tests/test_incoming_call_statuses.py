from unittest import TestCase
from unittest.mock import patch

from crm_lead_dedupe.leads.dup_utils import incoming_call_treat_as_new_statuses


class TestIncomingCallStatuses(TestCase):
    @patch("crm_lead_dedupe.leads.dup_utils.frappe.get_all", return_value=[])
    def test_empty_configuration_keeps_existing_lead_routing(self, get_all):
        self.assertEqual(incoming_call_treat_as_new_statuses(), set())

    @patch("crm_lead_dedupe.leads.dup_utils.frappe.get_all",
           return_value=[" Closed ", "Closed", "", None, " Lost "])
    def test_normalizes_configured_statuses(self, get_all):
        self.assertEqual(incoming_call_treat_as_new_statuses(), {"Closed", "Lost"})

    @patch("crm_lead_dedupe.leads.dup_utils.merge_statuses",
           side_effect=AssertionError("Merge settings must not affect incoming routing"))
    @patch("crm_lead_dedupe.leads.dup_utils.frappe.get_all", return_value=["Closed"])
    def test_reads_only_incoming_settings_child_rows(self, get_all, merge_statuses):
        self.assertEqual(incoming_call_treat_as_new_statuses(), {"Closed"})
        get_all.assert_called_once_with(
            "CRM Lead Dedupe Merge Status",
            filters={
                "parent": "CRM Lead Dedupe Settings",
                "parenttype": "CRM Lead Dedupe Settings",
                "parentfield": "incoming_call_treat_as_new_statuses",
            },
            pluck="crm_lead_status",
            order_by="idx asc",
        )
