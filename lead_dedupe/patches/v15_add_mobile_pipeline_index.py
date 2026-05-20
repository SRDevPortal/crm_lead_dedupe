import frappe

def execute():
    try:
        frappe.db.add_index("CRM Lead",
                            ["sr_mobile_norm", "sr_lead_pipeline"],
                            index_name="idx_crmlead_mobile_pipe")
    except Exception:
        pass
