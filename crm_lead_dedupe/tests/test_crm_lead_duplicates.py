from unittest import TestCase
from unittest.mock import patch

from crm_lead_dedupe.api.crm_lead_duplicates import (
    DEFAULT_MODAL_COLUMNS,
    get_allowed_modal_columns,
    get_effective_modal_columns,
    normalize_modal_columns,
)


class TestCRMLeadDuplicateModalColumns(TestCase):
    def test_default_modal_columns_are_used_when_missing(self):
        self.assertEqual(normalize_modal_columns(), list(DEFAULT_MODAL_COLUMNS))

    def test_unknown_columns_are_ignored(self):
        columns = normalize_modal_columns(["email", "password", "phone", "email"])

        self.assertEqual(columns, ["name", "email", "phone"])
        self.assertNotIn("password", columns)

    def test_name_column_is_always_required(self):
        self.assertEqual(normalize_modal_columns(["source"]), ["name", "source"])

    def test_json_encoded_columns_are_supported(self):
        columns = normalize_modal_columns('["pipeline", {"key": "country"}, "bad_field"]')

        self.assertEqual(columns, ["name", "pipeline", "country"])

    def test_allowed_columns_expose_expected_safe_fields(self):
        allowed = get_allowed_modal_columns()

        self.assertIn("mobile_no", allowed)
        self.assertIn("utm_campaign", allowed)
        self.assertNotIn("password", allowed)

    def test_non_system_manager_gets_default_columns_only(self):
        with patch(
            "crm_lead_dedupe.api.crm_lead_duplicates.can_customize_modal_columns",
            return_value=False,
        ):
            columns = get_effective_modal_columns(["name", "pipeline", "email"])

        self.assertEqual(columns, list(DEFAULT_MODAL_COLUMNS))

    def test_system_manager_can_request_allowed_columns(self):
        with patch(
            "crm_lead_dedupe.api.crm_lead_duplicates.can_customize_modal_columns",
            return_value=True,
        ):
            columns = get_effective_modal_columns(["pipeline", "password", "email"])

        self.assertEqual(columns, ["name", "pipeline", "email"])
