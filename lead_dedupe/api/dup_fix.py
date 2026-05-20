import frappe

def _is_newest(name: str) -> bool:
    d = frappe.get_doc("CRM Lead", name)
    if not d.get("sr_mobile_norm"):
        return False
    newest = frappe.db.get_value(
        "CRM Lead",
        {"sr_mobile_norm": d.sr_mobile_norm},
        "name",
        order_by="creation desc",
    )
    return newest == name

@frappe.whitelist()
def fix_duplicate_of_if_stale(name: str):
    """Clear sr_duplicate_of if target is missing, archived, or this row is the newest (primary)."""
    if not name or not frappe.db.exists("CRM Lead", name):
        return

    dup = frappe.db.get_value("CRM Lead", name, "sr_duplicate_of")
    if not dup:
        return

    clear = False
    if not frappe.db.exists("CRM Lead", dup):
        clear = True
    elif frappe.db.get_value("CRM Lead", dup, "sr_is_archived"):
        clear = True
    elif _is_newest(name):
        clear = True

    if clear:
        frappe.db.set_value("CRM Lead", name, {
            "sr_duplicate_of": None,
            "sr_is_duplicate": 0,
            "sr_duplicate_score": 0,
        }, update_modified=False)
        frappe.db.commit()
