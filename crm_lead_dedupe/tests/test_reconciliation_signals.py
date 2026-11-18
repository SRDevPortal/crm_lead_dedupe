import unittest
from unittest.mock import patch
from crm_lead_dedupe import reconciliation as mod


class SignalTests(unittest.TestCase):
    @patch.object(mod,"frappe")
    def test_bulk_update_signals_in_same_transaction(self,f):
        f.get_hooks.return_value=["consumer"]
        changes={"A":{"sr_dedupe_result":"Primary"},"B":{"sr_dedupe_pending":0}}
        mod.bulk_update("CRM Lead",changes,update_modified=False)
        f.db.bulk_update.assert_called_once_with("CRM Lead",changes,update_modified=False)
        f.get_attr.return_value.assert_called_once_with(["A"])
        f.db.commit.assert_not_called()

    @patch.object(mod,"frappe")
    def test_signal_failure_is_not_swallowed(self,f):
        f.get_hooks.return_value=["consumer"];f.get_attr.return_value.side_effect=RuntimeError("failed")
        with self.assertRaises(RuntimeError):mod.set_value("CRM Lead","A",{"sr_is_archived":1})

    @patch.object(mod,"frappe")
    def test_irrelevant_writes_do_not_signal(self,f):
        mod.set_value("CRM Lead","A",{"sr_mobile_norm":"123"})
        mod.bulk_update("Other",{"A":{"sr_is_duplicate":1}})
        f.get_hooks.assert_not_called()


if __name__=="__main__":unittest.main()
