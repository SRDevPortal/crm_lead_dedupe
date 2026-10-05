"""Customer-number privacy for CRM Lead dedupe browser and log boundaries."""
from __future__ import annotations

from copy import deepcopy
from functools import wraps
import re

import frappe


SENSITIVE_DOCTYPES = frozenset({
    "CRM Lead Auto Merge Log",
    "CRM Lead Dedupe Settings",
})
PHONE_KEYS = frozenset({
    "mobile",
    "mobile_no",
    "mobile_norm",
    "sr_mobile_norm",
    "last_mobile_norm",
    "normalized_phone",
    "phone",
    "phone_number",
})
RAW_KEYS = frozenset({
    "provider_response",
    "raw_payload",
    "raw_transport_payload",
    "payload",
})
TEXT_KEYS = frozenset({
    "lead_name",
    "error",
    "message",
    "reason",
    "warning",
})


def enabled() -> bool:
    return bool(frappe.conf.get("privacy_shield_desk_enabled", False)) and (
        "privacy_shield" in frappe.get_installed_apps()
    )


def restricted(user=None) -> bool:
    if not enabled():
        return False
    from privacy_shield.policy import current_capabilities

    return not current_capabilities(user).view_full


def project(payload):
    """Copy and redact a response without changing dedupe inputs or records."""
    from privacy_shield.display_text import mask_display
    from privacy_shield.masking import mask_number

    def clean(value, context=None):
        if isinstance(value, list):
            return [clean(item, context) for item in value]
        if isinstance(value, tuple):
            return tuple(clean(item, context) for item in value)
        if not isinstance(value, dict):
            if context in TEXT_KEYS and isinstance(value, str):
                return mask_display(value)
            return deepcopy(value)

        result = {}
        for key, item in value.items():
            if key in RAW_KEYS:
                continue
            if key in PHONE_KEYS:
                result[key] = (
                    item
                    if isinstance(item, str)
                    and re.fullmatch(r"\*{1,14}[0-9]{0,4}|\[masked\]", item)
                    else mask_number(item)
                )
            elif key in TEXT_KEYS:
                result[key] = clean(item, key)
            else:
                result[key] = clean(item, key)
        return result

    return clean(payload)


def browser_response(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        result = fn(*args, **kwargs)
        return project(result) if restricted() else result

    return wrapped


def require_full_number_visibility():
    if restricted():
        raise frappe.PermissionError(
            "This dedupe action requires full-number visibility."
        )


def check_sensitive_doctype(doctype, user=None):
    if doctype in SENSITIVE_DOCTYPES and restricted(user):
        raise frappe.PermissionError(
            "Dedupe number configuration and raw merge logs require full-number visibility."
        )


def has_permission(doc, ptype=None, user=None, debug=False):
    check_sensitive_doctype(doc.doctype, user)
    return None


def query_condition(user=None):
    return "1=0" if restricted(user) else ""


def guard_request():
    if not enabled():
        return
    request = getattr(frappe.local, "request", None)
    authorization = (
        getattr(request, "headers", {}).get("Authorization", "")
        if request is not None
        else ""
    )
    if authorization and getattr(frappe.session, "user", "Guest") == "Guest":
        return

    args = getattr(frappe.local, "form_dict", {}) or {}
    for key in ("doctype", "parent_doctype"):
        value = args.get(key)
        values = value if isinstance(value, list) else [value]
        for doctype in values:
            if isinstance(doctype, str):
                check_sensitive_doctype(doctype)

    if request and request.path.startswith("/api/"):
        from frappe.api import API_URL_MAP
        from werkzeug.exceptions import HTTPException

        try:
            _, arguments = API_URL_MAP.bind_to_environ(request.environ).match()
        except HTTPException:
            return
        check_sensitive_doctype(arguments.get("doctype"))
