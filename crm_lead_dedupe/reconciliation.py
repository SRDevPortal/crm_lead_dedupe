"""Notify optional consumers in the original transaction; never swallow signal failures."""
import frappe

WATCHED = {"sr_dedupe_result", "sr_dedupe_stage", "sr_is_duplicate", "sr_is_archived", "lead_owner", "sr_assignment_stage"}


def notify(updates):
    names = sorted(name for name, values in updates.items() if WATCHED.intersection(values))
    if not names:
        return
    for method in frappe.get_hooks("crm_lead_dedupe_state_changed"):
        frappe.get_attr(method)(names)


def bulk_update(doctype, updates, **kwargs):
    result = frappe.db.bulk_update(doctype, updates, **kwargs)
    if doctype == "CRM Lead": notify(updates)
    return result


def set_value(doctype, name, values, *args, **kwargs):
    result = frappe.db.set_value(doctype, name, values, *args, **kwargs)
    if doctype == "CRM Lead" and isinstance(name,str):
        changed = values if isinstance(values,dict) else {values: args[0] if args else None}
        notify({name:changed})
    return result
