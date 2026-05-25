import frappe
from frappe.utils import cint
from crm_lead_dedupe.logging import log_operation
from crm_lead_dedupe.leads.dup_utils import (
    DUPLICATE_THRESHOLD,
    find_dup_candidates,
    norm_mobile,
    score_duplicate,
)
from crm_lead_dedupe.leads.perm import (
    can_customize_modal_columns,
    can_manage_dedupe,
    require_lead_read,
)

DT = "CRM Lead"

DEFAULT_MODAL_COLUMNS = (
    "name",
    "owner",
    "stage",
    "creation",
    "mobile_no",
    "lead_name",
    "platform",
    "source",
    "score",
)

MODAL_COLUMN_FIELDS = {
    "name": ("name",),
    "owner": ("owner",),
    "stage": ("status", "sr_lead_disposition"),
    "creation": ("creation",),
    "mobile_no": ("mobile_no",),
    "lead_name": ("lead_name",),
    "platform": ("sr_lead_platform",),
    "source": ("source",),
    "score": (),
    "pipeline": ("sr_lead_pipeline",),
    "disposition": ("sr_lead_disposition",),
    "team": ("team",),
    "lead_owner": ("lead_owner",),
    "country": ("sr_lead_country",),
    "email": ("email",),
    "phone": ("phone",),
    "lead_score": ("lead_score",),
    "lead_temperature": ("lead_temperature",),
    "landing_page": ("sr_landing_page",),
    "utm_source": ("sr_utm_source",),
    "utm_campaign": ("sr_utm_campaign",),
    "utm_medium": ("sr_utm_medium",),
    "utm_term": ("sr_utm_term",),
    "gclid": ("sr_gclid",),
}


def normalize_modal_columns(columns=None) -> list[str]:
    keys = _as_column_list(columns) if columns else list(DEFAULT_MODAL_COLUMNS)

    normalized = []
    for key in keys:
        if isinstance(key, dict):
            key = key.get("key")
        if key in MODAL_COLUMN_FIELDS and key not in normalized:
            normalized.append(key)

    if not normalized:
        normalized = list(DEFAULT_MODAL_COLUMNS)
    if "name" not in normalized:
        normalized.insert(0, "name")

    return normalized


def get_allowed_modal_columns() -> list[str]:
    return list(MODAL_COLUMN_FIELDS)


def get_effective_modal_columns(columns=None, user=None) -> list[str]:
    if can_customize_modal_columns(user):
        return normalize_modal_columns(columns)
    return list(DEFAULT_MODAL_COLUMNS)


def _as_column_list(value):
    if isinstance(value, str):
        try:
            value = frappe.parse_json(value)
        except Exception:
            value = [value]
    if not isinstance(value, list):
        return []
    return [item for item in value if item]


def _db_fields_for_columns(columns) -> list[str]:
    fields = ["name"]
    for key in normalize_modal_columns(columns):
        for fieldname in MODAL_COLUMN_FIELDS[key]:
            if fieldname not in fields and frappe.db.has_column(DT, fieldname):
                fields.append(fieldname)
    return fields


def _column_value(key: str, row):
    if key == "stage":
        return row.get("sr_lead_disposition") or row.get("status")
    if key == "platform":
        return row.get("sr_lead_platform")
    if key == "pipeline":
        return row.get("sr_lead_pipeline")
    if key == "disposition":
        return row.get("sr_lead_disposition")
    if key == "country":
        return row.get("sr_lead_country")
    if key == "landing_page":
        return row.get("sr_landing_page")
    if key == "utm_source":
        return row.get("sr_utm_source")
    if key == "utm_campaign":
        return row.get("sr_utm_campaign")
    if key == "utm_medium":
        return row.get("sr_utm_medium")
    if key == "utm_term":
        return row.get("sr_utm_term")
    if key == "gclid":
        return row.get("sr_gclid")
    return row.get(key)


def _summary(name: str, columns=None) -> dict:
    """
    Fast, permission-agnostic fetch for just the fields we need in the modal.
    Using frappe.db.get_value bypasses PQC/permissions, so duplicates still show
    even if some are archived/hidden in the list.
    """
    column_keys = normalize_modal_columns(columns)
    row = frappe.db.get_value(
        DT,
        name,
        _db_fields_for_columns(column_keys),
        as_dict=True,
    ) or {}

    summary = {key: _column_value(key, row) for key in column_keys if key != "score"}
    summary["name"] = row.get("name") or name
    return summary

@frappe.whitelist()
def get_duplicates_for_crm_lead(lead_name: str, columns=None):
    """
    Duplicates by normalized mobile, excluding the primary.
    Returns columns: Lead Id, Owner, Stage, Creation, Mobile, Full Name,
    Platform, Source, Score.
    """
    if not lead_name:
        return []

    log_operation("get_duplicates.start", lead_name=lead_name)
    require_lead_read(lead_name)
    lead = frappe.get_doc("CRM Lead", lead_name)
    m = norm_mobile(lead.mobile_no or "")

    if not m:
        log_operation("get_duplicates.done", lead_name=lead_name, duplicate_count=0, reason="missing_mobile")
        return []

    column_keys = get_effective_modal_columns(columns)
    rows = []
    # find_dup_candidates should already return names for the same mobile
    for c in find_dup_candidates(
        m,
        exclude_name=lead.name,
        limit=50,
        pipeline=lead.get("sr_lead_pipeline"),
    ):
        s = score_duplicate(lead, c)
        if s < DUPLICATE_THRESHOLD:
            continue
        if not can_manage_dedupe() and not frappe.has_permission("CRM Lead", "read", c["name"]):
            continue
        r = _summary(c["name"], column_keys)
        r["score"] = s if s is not None else 100
        rows.append(r)

    # Sort: higher score first, then newest first
    rows.sort(key=lambda x: (x.get("score", 0), x.get("creation") or ""), reverse=True)
    log_operation("get_duplicates.done", lead_name=lead_name, duplicate_count=len(rows))
    return rows


@frappe.whitelist()
def get_hit_counts_for_crm_leads(lead_names):
    names = _as_list(lead_names)
    if not names:
        return {"success": True, "result": {}}

    log_operation("get_hit_counts.start", lead_count=len(names))
    result = {name: {"hit_count": 0, "unseen_hit": 0} for name in names}
    rows = frappe.get_all(
        DT,
        filters={"name": ["in", names]},
        fields=_count_fields(),
        limit_page_length=0,
    )
    rows_by_name = {row.name: row for row in rows}
    visible_rows = []

    for name in names:
        row = rows_by_name.get(name)
        if not row:
            continue
        if not frappe.has_permission("CRM Lead", "read", row.name):
            continue
        visible_rows.append(row)

    mobile_norms = {
        row.sr_mobile_norm or norm_mobile(row.mobile_no)
        for row in visible_rows
        if row.sr_mobile_norm or norm_mobile(row.mobile_no)
    }
    if not mobile_norms:
        log_operation("get_hit_counts.done", lead_count=len(names), mobile_group_count=0, candidate_count=0)
        return {"success": True, "result": result}

    candidate_rows = frappe.get_all(
        DT,
        filters={"sr_mobile_norm": ["in", list(mobile_norms)]},
        fields=_count_fields(),
        limit_page_length=0,
    )

    user_can_manage = can_manage_dedupe()
    permission_cache = {}
    candidates_by_mobile = {}

    for candidate in candidate_rows:
        candidate_mobile = candidate.sr_mobile_norm or norm_mobile(candidate.mobile_no)
        if not candidate_mobile:
            continue

        if not user_can_manage:
            if candidate.name not in permission_cache:
                permission_cache[candidate.name] = frappe.has_permission("CRM Lead", "read", candidate.name)
            if not permission_cache[candidate.name]:
                continue

        candidates_by_mobile.setdefault(candidate_mobile, []).append(candidate)

    for row in visible_rows:
        mobile_norm = row.sr_mobile_norm or norm_mobile(row.mobile_no)
        candidates = [
            candidate for candidate in candidates_by_mobile.get(mobile_norm, [])
            if candidate.name != row.name and score_duplicate(row, candidate) >= DUPLICATE_THRESHOLD
        ]

        result[row.name] = {
            "hit_count": len(candidates),
            "unseen_hit": cint(row.get("sr_dup_unseen_hit")),
        }

    log_operation(
        "get_hit_counts.done",
        lead_count=len(names),
        visible_count=len(visible_rows),
        mobile_group_count=len(mobile_norms),
        candidate_count=len(candidate_rows),
    )
    return {"success": True, "result": result}


@frappe.whitelist()
def acknowledge_duplicate_hit(lead_name: str):
    log_operation("acknowledge_duplicate_hit.start", lead_name=lead_name)
    require_lead_read(lead_name)

    if not frappe.db.has_column(DT, "sr_dup_unseen_hit"):
        log_operation("acknowledge_duplicate_hit.done", lead_name=lead_name, skipped="missing_column")
        return {"success": True}

    values = {"sr_dup_unseen_hit": 0}
    if frappe.db.has_column(DT, "sr_dup_unseen_hit_on"):
        values["sr_dup_unseen_hit_on"] = None

    frappe.db.set_value(DT, lead_name, values, update_modified=False)
    log_operation("acknowledge_duplicate_hit.done", lead_name=lead_name)
    return {"success": True}


def _as_list(value):
    if isinstance(value, str):
        try:
            value = frappe.parse_json(value)
        except Exception:
            value = [value]
    if not isinstance(value, list):
        return []
    return [item.get("name") if isinstance(item, dict) else item for item in value if item]


def _count_fields():
    fields = ["name", "mobile_no", "sr_mobile_norm"]
    if frappe.db.has_column("CRM Lead", "sr_lead_pipeline"):
        fields.append("sr_lead_pipeline")
    if frappe.db.has_column("CRM Lead", "sr_dup_unseen_hit"):
        fields.append("sr_dup_unseen_hit")
    return fields
