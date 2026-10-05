import json
import re

import frappe
from crm_lead_dedupe.settings import get_setting


LOGGER_NAME = "crm_lead_dedupe"


PHONE_TEXT = re.compile(r"(?<![0-9*])\+?[0-9](?:[0-9 ()+.-]*[0-9])?(?![0-9*])")


def mask_text(value):
    if not isinstance(value, str):
        return value

    def replace(match):
        token = match.group(0)
        digits = "".join(character for character in token if character.isdigit())
        if len(digits) < 7:
            return token
        return ("*" * max(len(digits) - 4, 1)) + digits[-4:]

    return PHONE_TEXT.sub(replace, value)


def _sanitize(value):
    if isinstance(value, dict):
        return {key: _sanitize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_sanitize(item) for item in value]
    return mask_text(value)


def _json_default(value):
    return str(value)


def _compact_context(context):
    compacted = {}
    for key, value in _sanitize(context).items():
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

    if get_setting("crm_lead_dedupe_console_log"):
        print(message, flush=True)
