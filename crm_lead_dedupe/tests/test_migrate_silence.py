from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from crm_lead_dedupe.migrate_silence import (
    SilentDBQueryProgressMonitor,
    get_config,
    install_silent_migrate_monitor,
)


class TestMigrateSilence(TestCase):
    def test_get_config_returns_marker_flag(self):
        self.assertEqual(get_config()["hide_migrate_query_progress"], 1)

    def test_monitor_replacement_is_noop(self):
        SilentDBQueryProgressMonitor().stop()

    def test_installs_silent_monitor_when_migrate_module_loaded(self):
        module = SimpleNamespace(DBQueryProgressMonitor=object)

        with patch.dict("sys.modules", {"frappe.migrate": module}):
            self.assertTrue(install_silent_migrate_monitor())

        self.assertIs(module.DBQueryProgressMonitor, SilentDBQueryProgressMonitor)
