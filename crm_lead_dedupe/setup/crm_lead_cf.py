# apps/crm_lead_dedupe/crm_lead_dedupe/setup/crm_lead_cf.py
import frappe

from crm_lead_dedupe.leads.dup_utils import norm_mobile, recompute_hit_counts

DT = "CRM Lead"
CUSTOM_FIELDS = [
    # Dedupe
    {"fieldname": "sr_dedupe_tab", "label": "Duplicates", "fieldtype": "Tab Break", "insert_after": "sr_w_team_id"},
    {"fieldname": "sr_dedupe_sec", "label": "", "fieldtype": "Section Break", "insert_after": "sr_dedupe_tab"},
    {
        "fieldname": "sr_mobile_norm",
        "label": "Mobile (Normalized)",
        "fieldtype": "Data",
        "insert_after": "sr_dedupe_sec",
        "hidden": 1,
        "read_only": 1,
    },
    {
        "fieldname": "sr_duplicate_of",
        "label": "Duplicate Of",
        "fieldtype": "Link",
        "options": "CRM Lead",
        "insert_after": "sr_mobile_norm",
        "hidden": 1,
        "read_only": 1,
    },
    {
        "fieldname": "sr_duplicate_score",
        "label": "Duplicate Score",
        "fieldtype": "Float",
        "insert_after": "sr_duplicate_of",
        "default": 0,
        "hidden": 1,
        "read_only": 1,
    },
    {
        "fieldname": "sr_is_duplicate",
        "label": "Is Duplicate",
        "fieldtype": "Check",
        "insert_after": "sr_duplicate_score",
        "hidden": 1,
        "default": 0,
    },
    {
        "fieldname": "sr_dup_candidates_json",
        "label": "Dup Candidates (JSON)",
        "fieldtype": "Small Text",
        "insert_after": "sr_is_duplicate",
        "hidden": 1,
    },
    {
        "fieldname": "sr_dup_hit_count",
        "label": "Dup Hit Count",
        "fieldtype": "Int",
        "insert_after": "sr_dup_candidates_json",
        "default": 0,
        "hidden": 1,
    },
    {
        "fieldname": "sr_is_archived",
        "label": "Archived (Hidden)",
        "fieldtype": "Check",
        "default": "0",
        "insert_after": "sr_dup_hit_count",
        "in_list_view": 0,
        "in_standard_filter": 0,
        "read_only": 1,
    },
]


def apply():
    if not frappe.db.exists("DocType", DT):
        return False

    changed = False

    def add_cf(df):
        nonlocal changed
        if not frappe.db.exists("Custom Field", {"dt": DT, "fieldname": df["fieldname"]}):
            cf = frappe.get_doc({"doctype": "Custom Field", "dt": DT, **df})
            cf.insert(ignore_permissions=True)
            changed = True

    for df in CUSTOM_FIELDS:
        add_cf(df)

    if changed:
        frappe.clear_cache(doctype=DT)

    ensure_indexes()
    backfill_mobile_norm()
    return True


def ensure_indexes():
    if not frappe.db.has_column(DT, "sr_mobile_norm"):
        return

    try:
        frappe.db.add_index(DT, ["sr_mobile_norm"], index_name="idx_crmlead_mobile_norm")
    except Exception:
        pass


def backfill_mobile_norm():
    if not frappe.db.has_column(DT, "mobile_no") or not frappe.db.has_column(DT, "sr_mobile_norm"):
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
                DT,
                row.name,
                "sr_mobile_norm",
                mobile_norm,
                update_modified=False,
            )

    if not frappe.db.has_column(DT, "sr_dup_hit_count"):
        return

    for mobile_norm in mobile_groups:
        recompute_hit_counts(mobile_norm)

    if not frappe.db.has_column(DT, "sr_lead_pipeline"):
        return

    try:
        frappe.db.add_index(
            DT,
            ["sr_mobile_norm", "sr_lead_pipeline"],
            index_name="idx_crmlead_mobile_pipe",
        )
    except Exception:
        pass

