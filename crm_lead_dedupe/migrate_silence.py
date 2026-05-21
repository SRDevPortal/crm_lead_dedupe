import sys


class SilentDBQueryProgressMonitor:
    """No-op replacement for Frappe's migrate query progress printer."""

    def stop(self):
        pass


def install_silent_migrate_monitor():
    migrate_module = sys.modules.get("frappe.migrate")
    if not migrate_module:
        return False

    migrate_module.DBQueryProgressMonitor = SilentDBQueryProgressMonitor
    return True


def get_config():
    install_silent_migrate_monitor()
    return {"hide_migrate_query_progress": 1}
