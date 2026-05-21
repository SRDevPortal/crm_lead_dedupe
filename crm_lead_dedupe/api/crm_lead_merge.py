import frappe
from frappe import _
from frappe.model.rename_doc import rename_doc
from crm_lead_dedupe.leads.dup_utils import (
    DUPLICATE_OF_FIELD,
    LEGACY_DUPLICATE_OF_FIELD,
    DUPLICATE_THRESHOLD,
    norm_mobile,
    score_duplicate,
    sync_duplicate_group,
)
from crm_lead_dedupe.leads.perm import require_dedupe_manager
from crm_lead_dedupe.integrations.wa_chat_hub import relink_crm_lead_conversations


def _as_list(value):
    if isinstance(value, str):
        try:
            value = frappe.parse_json(value)
        except Exception:
            value = [d.strip() for d in value.split(",") if d.strip()]
    if not isinstance(value, list):
        return []
    return [item.get("name") if isinstance(item, dict) else item for item in value if item]


def _lead_row(name: str) -> frappe._dict:
    fields = [
        "name",
        "mobile_no",
        "sr_mobile_norm",
        "sr_lead_pipeline",
        "sr_lead_platform",
        "lead_name",
        "status",
        "source",
        "sr_is_archived",
    ]
    existing_fields = [field for field in fields if field == "name" or frappe.db.has_column("CRM Lead", field)]
    row = frappe.db.get_value("CRM Lead", name, existing_fields, as_dict=True)
    if not row:
        frappe.throw(_("CRM Lead {0} does not exist.").format(name))
    row.sr_mobile_norm = row.get("sr_mobile_norm") or norm_mobile(row.get("mobile_no"))
    return row


def _validate_duplicate(primary_row, duplicate_row):
    if not primary_row.sr_mobile_norm:
        frappe.throw(_("Primary lead has no normalized mobile number."))
    if primary_row.sr_mobile_norm != duplicate_row.sr_mobile_norm:
        frappe.throw(
            _("Lead {0} does not share the primary mobile number.").format(duplicate_row.name)
        )

    score = score_duplicate(primary_row, duplicate_row)
    if score < DUPLICATE_THRESHOLD:
        frappe.throw(
            _("Lead {0} is below the duplicate confidence threshold.").format(duplicate_row.name)
        )

@frappe.whitelist()
def merge_crm_leads(primary: str, duplicates):
    require_dedupe_manager()

    duplicates = _as_list(duplicates)
    if not duplicates:
        frappe.throw("No duplicates provided.")

    primary_row = _lead_row(primary)
    if primary_row.get("sr_is_archived"):
        frappe.throw(_("Primary lead is archived. Choose the active lead as primary."))

    allowed_duplicates = []
    for d in duplicates:
        if d == primary:
            continue
        duplicate_row = _lead_row(d)
        _validate_duplicate(primary_row, duplicate_row)
        allowed_duplicates.append(d)

    if not allowed_duplicates:
        frappe.throw("No valid duplicates provided.")

    relink_crm_lead_conversations(primary, allowed_duplicates)

    # merge each duplicate into primary
    for d in allowed_duplicates:
        rename_doc("CRM Lead", d, primary, force=True, merge=True, ignore_permissions=True)

    # primary must be clean (not a duplicate of anything)
    values = {
        "sr_is_duplicate": 0,
        DUPLICATE_OF_FIELD: None,
        "sr_duplicate_score": 0,
    }
    if frappe.db.has_column("CRM Lead", LEGACY_DUPLICATE_OF_FIELD):
        values[LEGACY_DUPLICATE_OF_FIELD] = None
    frappe.db.set_value("CRM Lead", primary, values, update_modified=False)

    sync_duplicate_group(primary_row.sr_mobile_norm, primary_row.get("sr_lead_pipeline"))

    frappe.db.commit()
    return {"status": "ok", "primary": primary, "merged": allowed_duplicates}
