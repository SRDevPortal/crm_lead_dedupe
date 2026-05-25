import json

import frappe


LOGGER_NAME = "crm_lead_dedupe"


def _json_default(value):
    return str(value)


def _compact_context(context):
    compacted = {}
    for key, value in context.items():
        if value is None:
            continue
        if isinstance(value, (list, tuple, set)):
            compacted[key] = list(value)[:20]
            if len(value) > 20:
                compacted[f"{key}_truncated"] = len(value) - 20
        else:
            compacted[key] = value
    return compacted


def log_operation(event, **context):
    """Write one compact operation line to both Frappe logs and server stdout."""
    context = _compact_context(context)
    user = getattr(frappe.session, "user", None) if getattr(frappe, "session", None) else None
    site = getattr(frappe.local, "site", None) if getattr(frappe, "local", None) else None
    payload = {
        "event": event,
        "site": site,
        "user": user,
        **context,
    }
    message = f"[{LOGGER_NAME}] {json.dumps(payload, default=_json_default, sort_keys=True)}"

    try:
        frappe.logger(LOGGER_NAME).info(message)
    except Exception:
        pass

    if frappe.conf.get("crm_lead_dedupe_console_log", 1):
        print(message, flush=True)
