import frappe


SETTINGS_DOCTYPE = "CRM Lead Dedupe Settings"

SETTING_DEFAULTS = {
    "crm_lead_dedupe_enabled": 1,
    "crm_lead_dedupe_ui_enabled": 1,
    "crm_lead_dedupe_hooks_enabled": 1,
    "crm_lead_dedupe_archive_enabled": 1,
    "crm_lead_dedupe_merge_enabled": 1,
    "crm_lead_dedupe_scheduler_enabled": 1,
    "crm_lead_dedupe_hit_count_enabled": 1,
    "crm_lead_dedupe_permission_filter_enabled": 1,
    "crm_lead_dedupe_match_by_pipeline_enabled": 0,
    "crm_lead_dedupe_newest_primary_enabled": 0,
    "crm_lead_dedupe_oldest_primary_enabled": 0,
    "crm_lead_dedupe_merge_statuses": "",
    "crm_lead_dedupe_console_log": 1,
    "crm_lead_dedupe_max_pending_leads": 2000,
    "crm_lead_dedupe_max_mobile_groups": 500,
    "crm_lead_dedupe_max_merges_per_run": 100,
    "crm_lead_dedupe_max_group_size": 100,
    "crm_lead_dedupe_scheduler_interval_minutes": 5,
    "crm_lead_dedupe_blocked_mobiles": "\n".join(
        [
            "0000000000",
            "1111111111",
            "2222222222",
            "3333333333",
            "4444444444",
            "5555555555",
            "6666666666",
            "7777777777",
            "8888888888",
            "9999999999",
            "1234567890",
        ]
    ),
}

FEATURE_KEYS = {
    "ui": "crm_lead_dedupe_ui_enabled",
    "hooks": "crm_lead_dedupe_hooks_enabled",
    "archive": "crm_lead_dedupe_archive_enabled",
    "merge": "crm_lead_dedupe_merge_enabled",
    "scheduler": "crm_lead_dedupe_scheduler_enabled",
    "hit_count": "crm_lead_dedupe_hit_count_enabled",
    "permission_filter": "crm_lead_dedupe_permission_filter_enabled",
    "console_log": "crm_lead_dedupe_console_log",
}


def _as_bool(value, default=True):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value)
    return str(value).strip().lower() not in {"0", "false", "no", "off", "disabled"}


def _site_config_has(key):
    try:
        return frappe.conf.get(key) is not None
    except Exception:
        return False


def _ui_setting(key):
    try:
        if not getattr(frappe, "db", None):
            return None
        if not frappe.db.exists("DocType", SETTINGS_DOCTYPE):
            return None
        return frappe.db.get_single_value(SETTINGS_DOCTYPE, key)
    except Exception:
        return None


def ensure_settings_defaults():
    try:
        if not getattr(frappe, "db", None):
            return False
        if not frappe.db.exists("DocType", SETTINGS_DOCTYPE):
            return False

        changed = False
        for key, value in SETTING_DEFAULTS.items():
            exists = frappe.db.exists("Singles", {"doctype": SETTINGS_DOCTYPE, "field": key})
            if exists:
                continue
            frappe.db.set_single_value(SETTINGS_DOCTYPE, key, value)
            changed = True

        return changed
    except Exception:
        return False


def get_setting(key):
    default = SETTING_DEFAULTS.get(key, 1)

    # Explicit site_config values are emergency overrides and win over the UI.
    if _site_config_has(key):
        value = frappe.conf.get(key)
        if isinstance(default, bool) or key in FEATURE_KEYS.values() or key.endswith("_enabled") or key.endswith("_log"):
            return _as_bool(value, bool(default))
        return value

    ui_value = _ui_setting(key)
    if ui_value is not None:
        if isinstance(default, bool) or key in FEATURE_KEYS.values() or key.endswith("_enabled") or key.endswith("_log"):
            return _as_bool(ui_value, bool(default))
        return ui_value

    return default


def is_enabled(feature: str | None = None) -> bool:
    if not get_setting("crm_lead_dedupe_enabled"):
        return False
    if not feature:
        return True
    key = FEATURE_KEYS.get(feature, feature)
    return get_setting(key)


def as_boot_dict():
    return {
        "enabled": is_enabled(),
        "ui_enabled": is_enabled("ui"),
        "hooks_enabled": is_enabled("hooks"),
        "archive_enabled": is_enabled("archive"),
        "merge_enabled": is_enabled("merge"),
        "scheduler_enabled": is_enabled("scheduler"),
        "hit_count_enabled": is_enabled("hit_count"),
        "permission_filter_enabled": is_enabled("permission_filter"),
        "match_by_pipeline_enabled": get_setting("crm_lead_dedupe_match_by_pipeline_enabled"),
        "newest_primary_enabled": get_setting("crm_lead_dedupe_newest_primary_enabled"),
        "oldest_primary_enabled": get_setting("crm_lead_dedupe_oldest_primary_enabled"),
        "merge_statuses": get_setting("crm_lead_dedupe_merge_statuses"),
        "console_log": get_setting("crm_lead_dedupe_console_log"),
        "scheduler_interval_minutes": get_setting("crm_lead_dedupe_scheduler_interval_minutes"),
    }


def boot_session(bootinfo):
    bootinfo.crm_lead_dedupe = as_boot_dict()
