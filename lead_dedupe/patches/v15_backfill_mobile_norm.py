import frappe
from lead_dedupe.leads.dup_utils import norm_mobile, recompute_hit_counts


def execute():
    if not frappe.db.exists("DocType", "CRM Lead"):
        return

    rows = frappe.db.sql(
        """
        select name, mobile_no, sr_mobile_norm
        from `tabCRM Lead`
        where ifnull(mobile_no, '') != ''
        order by creation asc
        """,
        as_dict=True,
    )

    mobile_groups = set()
    for row in rows:
        mobile_norm = norm_mobile(row.mobile_no)
        if not mobile_norm:
            continue

        mobile_groups.add(mobile_norm)
        if row.sr_mobile_norm != mobile_norm:
            frappe.db.set_value(
                "CRM Lead",
                row.name,
                "sr_mobile_norm",
                mobile_norm,
                update_modified=False,
            )

    for mobile_norm in mobile_groups:
        recompute_hit_counts(mobile_norm)
