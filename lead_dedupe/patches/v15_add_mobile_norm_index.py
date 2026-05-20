import frappe


def execute():
    try:
        frappe.db.add_index(
            "CRM Lead",
            ["sr_mobile_norm"],
            index_name="idx_crmlead_mobile_norm",
        )
    except Exception:
        pass
