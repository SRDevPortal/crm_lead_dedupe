# apps/crm_lead_dedupe/crm_lead_dedupe/setup/crm_lead_cf.py
import frappe

from crm_lead_dedupe.leads.dup_utils import (
    DUPLICATE_OF_FIELD,
    LEGACY_DUPLICATE_OF_FIELD,
    norm_mobile,
    sync_duplicate_group,
)

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
        "fieldname": DUPLICATE_OF_FIELD,
        "label": "Duplicate Of (Name)",
        "fieldtype": "Data",
        "insert_after": "sr_mobile_norm",
        "hidden": 1,
        "read_only": 1,
    },
    {
        "fieldname": "sr_duplicate_score",
        "label": "Duplicate Score",
        "fieldtype": "Float",
        "insert_after": DUPLICATE_OF_FIELD,
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
        "read_only": 1,
    },
    {
        "fieldname": "sr_dup_candidates_json",
        "label": "Dup Candidates (JSON)",
        "fieldtype": "Small Text",
        "insert_after": "sr_is_duplicate",
        "hidden": 1,
        "read_only": 1,
    },
    {
        "fieldname": "sr_dup_hit_count",
        "label": "Dup Hit Count",
        "fieldtype": "Int",
        "insert_after": "sr_dup_candidates_json",
        "default": 0,
        "hidden": 1,
        "read_only": 1,
    },
    {
        "fieldname": "sr_dup_unseen_hit",
        "label": "Unseen Duplicate Hit",
        "fieldtype": "Check",
        "insert_after": "sr_dup_hit_count",
        "default": 0,
        "hidden": 1,
        "read_only": 1,
    },
    {
        "fieldname": "sr_dup_unseen_hit_on",
        "label": "Unseen Duplicate Hit On",
        "fieldtype": "Datetime",
        "insert_after": "sr_dup_unseen_hit",
        "hidden": 1,
        "read_only": 1,
    },
    {
        "fieldname": "sr_is_archived",
        "label": "Archived (Hidden)",
        "fieldtype": "Check",
        "default": "0",
        "insert_after": "sr_dup_unseen_hit_on",
        "in_list_view": 0,
        "in_standard_filter": 0,
        "read_only": 1,
    },
]


def apply():
    if not frappe.db.exists("DocType", DT):
        return False

    changed = False

    def sync_cf(df):
        nonlocal changed
        existing = frappe.db.get_value("Custom Field", {"dt": DT, "fieldname": df["fieldname"]}, "name")
        if not existing:
            cf = frappe.get_doc({"doctype": "Custom Field", "dt": DT, **df})
            cf.insert(ignore_permissions=True)
            changed = True
            return

        cf = frappe.get_doc("Custom Field", existing)
        field_changed = False
        for key, value in df.items():
            if cf.get(key) != value:
                cf.set(key, value)
                field_changed = True
        if field_changed:
            cf.save(ignore_permissions=True)
            changed = True

    for df in CUSTOM_FIELDS:
        sync_cf(df)

    if changed:
        frappe.clear_cache(doctype=DT)

    ensure_indexes()
    clear_legacy_duplicate_links()
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

    has_pipeline = frappe.db.has_column(DT, "sr_lead_pipeline")
    pipeline_select = ", sr_lead_pipeline" if has_pipeline else ""
    rows = frappe.db.sql(
        f"""
        select name, mobile_no, sr_mobile_norm {pipeline_select}
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

        mobile_groups.add((mobile_norm, row.get("sr_lead_pipeline") if has_pipeline else None))
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

    for mobile_norm, pipeline in mobile_groups:
        sync_duplicate_group(mobile_norm, pipeline)

    if not has_pipeline:
        return

    try:
        frappe.db.add_index(
            DT,
            ["sr_mobile_norm", "sr_lead_pipeline"],
            index_name="idx_crmlead_mobile_pipe",
        )
    except Exception:
        pass


def clear_legacy_duplicate_links():
    if not frappe.db.has_column(DT, LEGACY_DUPLICATE_OF_FIELD):
        return

    frappe.db.sql(
        f"""
        update `tab{DT}`
        set `{LEGACY_DUPLICATE_OF_FIELD}` = null
        where ifnull(`{LEGACY_DUPLICATE_OF_FIELD}`, '') != ''
        """
    )

