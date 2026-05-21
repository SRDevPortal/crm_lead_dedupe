from unittest import TestCase

from crm_lead_dedupe.api.crm_doc_guard import force_active_crm_lead_filters
from crm_lead_dedupe import hooks


class TestCRMDocGuard(TestCase):
    def test_crm_lead_filters_are_forced_active(self):
        filters, default_filters = force_active_crm_lead_filters(
            "CRM Lead",
            {"status": "Fresh", "sr_is_archived": 1},
            {"converted": 1},
        )

        self.assertEqual(filters["status"], "Fresh")
        self.assertEqual(filters["sr_is_archived"], 0)
        self.assertEqual(filters["converted"], 0)
        self.assertEqual(default_filters["sr_is_archived"], 0)
        self.assertEqual(default_filters["converted"], 0)

    def test_non_crm_lead_filters_are_not_changed(self):
        filters = {"disabled": 0}
        default_filters = {"name": ["like", "A%"]}

        result = force_active_crm_lead_filters("User", filters, default_filters)

        self.assertEqual(result, (filters, default_filters))

    def test_crm_get_data_is_overridden(self):
        self.assertEqual(
            hooks.override_whitelisted_methods["crm.api.doc.get_data"],
            "crm_lead_dedupe.api.crm_doc_guard.get_data",
        )
