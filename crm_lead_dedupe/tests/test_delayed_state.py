from unittest import TestCase
from unittest.mock import patch

import frappe

from crm_lead_dedupe.leads.dup_hooks import _input_hash, _metadata_missing


class TestDelayedDedupeState(TestCase):
    def test_input_hash_changes_with_pipeline_and_source(self):
        base = frappe._dict(sr_mobile_norm="9876543210", sr_lead_pipeline="Skin", source="Meta")
        changed = frappe._dict(sr_mobile_norm="9876543210", sr_lead_pipeline="Kidney", source="Meta")

        self.assertNotEqual(_input_hash(base), _input_hash(changed))

    def test_required_metadata_is_reported(self):
        def setting(key):
            return 1 if key in {"crm_lead_dedupe_require_pipeline", "crm_lead_dedupe_require_source"} else 0

        with patch("crm_lead_dedupe.leads.dup_hooks.get_setting", side_effect=setting):
            self.assertEqual(
                _metadata_missing(frappe._dict(sr_lead_pipeline=None, source=None)),
                ["pipeline", "source"],
            )

    def test_optional_metadata_does_not_block(self):
        with patch("crm_lead_dedupe.leads.dup_hooks.get_setting", return_value=0):
            self.assertEqual(_metadata_missing(frappe._dict()), [])
