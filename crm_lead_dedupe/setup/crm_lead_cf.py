# apps/crm_lead_dedupe/crm_lead_dedupe/setup/crm_lead_cf.py
import time

import frappe
from crm_lead_dedupe.leads.perm import require_dedupe_manager

from crm_lead_dedupe.leads.dup_utils import (
    DUPLICATE_OF_FIELD,
    LEGACY_DUPLICATE_OF_FIELD,
    norm_mobile,
    sync_duplicate_group,
)

DT = "CRM Lead"
PROGRESS_PREFIX = "crm_lead_dedupe_backfill"
LOGGER_NAME = "crm_lead_dedupe_backfill"
CUSTOM_FIELDS = [
    # Dedupe
    {"fieldname": "sr_dedupe_tab", "label": "Duplicates", "fieldtype": "Tab Break", "insert_after": "sr_w_team_id"},
    {"fieldname": "sr_dedupe_sec", "label": "", "fieldtype": "Section Break", "insert_after": "sr_dedupe_tab"},
    {
        "fieldname": "sr_mobile_norm",
        "label": "Mobile (Normalized)",
        "fieldtype": "Data",
        "insert_after": "sr_dedupe_sec",
        "search_index": 1,
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
        "default": "0",
        "hidden": 1,
        "read_only": 1,
    },
    {
        "fieldname": "sr_is_duplicate",
        "label": "Is Duplicate",
        "fieldtype": "Check",
        "insert_after": "sr_duplicate_score",
        "hidden": 1,
        "default": "0",
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
        "default": "0",
        "hidden": 1,
        "read_only": 1,
    },
    {
        "fieldname": "sr_dup_unseen_hit",
        "label": "Unseen Duplicate Hit",
        "fieldtype": "Check",
        "insert_after": "sr_dup_hit_count",
        "default": "0",
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


def apply(run_backfill: bool = False):
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
    if run_backfill:
        return run_backfill_batch()
    return True


def _progress_key(key: str) -> str:
    return f"{PROGRESS_PREFIX}_{key}"


def _get_progress(key: str, default: str = "") -> str:
    return frappe.defaults.get_global_default(_progress_key(key)) or default


def _set_progress(key: str, value) -> None:
    frappe.defaults.set_global_default(_progress_key(key), value)


def _is_done(key: str) -> bool:
    return _get_progress(key) == "1"


def _as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _log_backfill(message: str, log_to_console: bool = True) -> None:
    frappe.logger(LOGGER_NAME).info(message)
    if _as_bool(log_to_console):
        print(f"[{LOGGER_NAME}] {message}")


@frappe.whitelist()
def reset_backfill_progress():
    require_dedupe_manager()
    for key in (
        "legacy_done",
        "normalize_done",
        "normalize_last_name",
        "groups_done",
        "groups_last_mobile_norm",
    ):
        frappe.defaults.set_global_default(_progress_key(key), None)
    frappe.db.commit()
    return {"reset": True}


def ensure_indexes():
    if not frappe.db.has_column(DT, "sr_mobile_norm"):
        return

    if not frappe.db.get_column_index(f"tab{DT}", "sr_mobile_norm", unique=False):
        try:
            frappe.db.add_index(DT, ["sr_mobile_norm"], index_name="idx_crmlead_mobile_norm")
        except Exception:
            pass

    if frappe.db.has_column(DT, "sr_lead_pipeline"):
        try:
            frappe.db.add_index(
                DT,
                ["sr_mobile_norm", "sr_lead_pipeline"],
                index_name="idx_crmlead_mobile_pipe",
            )
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


@frappe.whitelist()
def clear_legacy_duplicate_links_batched(
    batch_size: int = 5000,
    reset: bool = False,
    log_records: bool = False,
    log_to_console: bool = True,
):
    require_dedupe_manager()
    log_records = _as_bool(log_records)
    if not frappe.db.has_column(DT, LEGACY_DUPLICATE_OF_FIELD):
        _set_progress("legacy_done", "1")
        frappe.db.commit()
        result = {"processed": 0, "done": True}
        _log_backfill(f"legacy_links skipped: column_missing result={result}", log_to_console)
        return result

    if reset:
        _set_progress("legacy_done", None)

    if _is_done("legacy_done"):
        result = {"processed": 0, "done": True}
        _log_backfill(f"legacy_links skipped: already_done result={result}", log_to_console)
        return result

    batch_size = max(1, int(batch_size or 5000))
    rows = frappe.db.sql(
        f"""
        select name
        from `tab{DT}`
        where ifnull(`{LEGACY_DUPLICATE_OF_FIELD}`, '') != ''
        order by name asc
        limit %(batch_size)s
        """,
        {"batch_size": batch_size},
        as_dict=True,
    )

    if not rows:
        _set_progress("legacy_done", "1")
        frappe.db.commit()
        result = {"processed": 0, "done": True}
        _log_backfill(f"legacy_links batch result={result}", log_to_console)
        return result

    names = [row.name for row in rows]
    frappe.db.sql(
        f"""
        update `tab{DT}`
        set `{LEGACY_DUPLICATE_OF_FIELD}` = null
        where name in %(names)s
        """,
        {"names": names},
    )
    done = len(names) < batch_size
    if done:
        _set_progress("legacy_done", "1")
    frappe.db.commit()
    result = {"processed": len(names), "done": done}
    _log_backfill(f"legacy_links batch result={result}", log_to_console)
    if log_records:
        _log_backfill(f"legacy_links cleared_names={names}", log_to_console)
    return result


@frappe.whitelist()
def backfill_mobile_norm_batched(
    batch_size: int = 2000,
    reset: bool = False,
    log_records: bool = False,
    log_to_console: bool = True,
):
    require_dedupe_manager()
    log_records = _as_bool(log_records)
    if not frappe.db.has_column(DT, "mobile_no") or not frappe.db.has_column(DT, "sr_mobile_norm"):
        _set_progress("normalize_done", "1")
        frappe.db.commit()
        result = {"processed": 0, "updated": 0, "done": True}
        _log_backfill(f"normalize skipped: column_missing result={result}", log_to_console)
        return result

    if reset:
        _set_progress("normalize_done", None)
        _set_progress("normalize_last_name", "")

    if _is_done("normalize_done"):
        result = {
            "processed": 0,
            "updated": 0,
            "last_name": _get_progress("normalize_last_name"),
            "done": True,
        }
        _log_backfill(f"normalize skipped: already_done result={result}", log_to_console)
        return result

    batch_size = max(1, int(batch_size or 2000))
    last_name = _get_progress("normalize_last_name")
    rows = frappe.db.sql(
        f"""
        select name, mobile_no, sr_mobile_norm
        from `tab{DT}`
        where ifnull(mobile_no, '') != ''
            and name > %(last_name)s
        order by name asc
        limit %(batch_size)s
        """,
        {"last_name": last_name, "batch_size": batch_size},
        as_dict=True,
    )

    if not rows:
        _set_progress("normalize_done", "1")
        frappe.db.commit()
        result = {"processed": 0, "updated": 0, "last_name": last_name, "done": True}
        _log_backfill(f"normalize batch result={result}", log_to_console)
        return result

    updates = {}
    for row in rows:
        mobile_norm = norm_mobile(row.mobile_no)
        if mobile_norm and row.sr_mobile_norm != mobile_norm:
            updates[row.name] = {"sr_mobile_norm": mobile_norm}

    if updates:
        try:
            frappe.db.bulk_update(DT, updates, update_modified=False)
        except Exception:
            for name, values in updates.items():
                frappe.db.set_value(DT, name, values, update_modified=False)

    last_name = rows[-1].name
    done = len(rows) < batch_size
    _set_progress("normalize_last_name", last_name)
    if done:
        _set_progress("normalize_done", "1")
    frappe.db.commit()

    result = {
        "processed": len(rows),
        "updated": len(updates),
        "last_name": last_name,
        "done": done,
    }
    _log_backfill(f"normalize batch result={result}", log_to_console)
    if log_records:
        _log_backfill(f"normalize updated_names={list(updates)}", log_to_console)
    return result


@frappe.whitelist()
def sync_duplicate_groups_batched(
    batch_size: int = 500,
    reset: bool = False,
    log_records: bool = False,
    log_to_console: bool = True,
):
    require_dedupe_manager()
    log_records = _as_bool(log_records)
    if not frappe.db.has_column(DT, "sr_mobile_norm") or not frappe.db.has_column(DT, "sr_dup_hit_count"):
        _set_progress("groups_done", "1")
        frappe.db.commit()
        result = {"processed": 0, "done": True}
        _log_backfill(f"group_sync skipped: column_missing result={result}", log_to_console)
        return result

    if reset:
        _set_progress("groups_done", None)
        _set_progress("groups_last_mobile_norm", "")

    if _is_done("groups_done"):
        result = {
            "processed": 0,
            "last_mobile_norm": _get_progress("groups_last_mobile_norm"),
            "done": True,
        }
        _log_backfill(f"group_sync skipped: already_done result={result}", log_to_console)
        return result

    batch_size = max(1, int(batch_size or 500))
    last_mobile_norm = _get_progress("groups_last_mobile_norm")
    rows = frappe.db.sql(
        f"""
        select sr_mobile_norm
        from `tab{DT}`
        where ifnull(sr_mobile_norm, '') != ''
            and sr_mobile_norm > %(last_mobile_norm)s
        group by sr_mobile_norm
        order by sr_mobile_norm asc
        limit %(batch_size)s
        """,
        {"last_mobile_norm": last_mobile_norm, "batch_size": batch_size},
        as_dict=True,
    )

    if not rows:
        _set_progress("groups_done", "1")
        frappe.db.commit()
        result = {"processed": 0, "last_mobile_norm": last_mobile_norm, "done": True}
        _log_backfill(f"group_sync batch result={result}", log_to_console)
        return result

    mobile_norms = [row.sr_mobile_norm for row in rows]
    for row in rows:
        sync_duplicate_group(row.sr_mobile_norm)

    last_mobile_norm = rows[-1].sr_mobile_norm
    done = len(rows) < batch_size
    _set_progress("groups_last_mobile_norm", last_mobile_norm)
    if done:
        _set_progress("groups_done", "1")
    frappe.db.commit()

    result = {
        "processed": len(rows),
        "last_mobile_norm": last_mobile_norm,
        "done": done,
    }
    _log_backfill(f"group_sync batch result={result}", log_to_console)
    if log_records:
        _log_backfill(f"group_sync mobile_norms={mobile_norms}", log_to_console)
    return result


@frappe.whitelist()
def run_backfill_batch(
    legacy_batch_size: int = 5000,
    normalize_batch_size: int = 2000,
    group_batch_size: int = 500,
    log_records: bool = False,
    log_to_console: bool = True,
):
    require_dedupe_manager()
    log_records = _as_bool(log_records)
    ensure_indexes()

    legacy = clear_legacy_duplicate_links_batched(
        batch_size=legacy_batch_size,
        log_records=log_records,
        log_to_console=log_to_console,
    )
    normalize = {"processed": 0, "updated": 0, "done": _is_done("normalize_done")}
    groups = {"processed": 0, "done": _is_done("groups_done")}

    if legacy.get("done"):
        normalize = backfill_mobile_norm_batched(
            batch_size=normalize_batch_size,
            log_records=log_records,
            log_to_console=log_to_console,
        )

    if legacy.get("done") and normalize.get("done"):
        groups = sync_duplicate_groups_batched(
            batch_size=group_batch_size,
            log_records=log_records,
            log_to_console=log_to_console,
        )

    result = {
        "legacy": legacy,
        "normalize": normalize,
        "groups": groups,
        "done": bool(legacy.get("done") and normalize.get("done") and groups.get("done")),
    }
    _log_backfill(f"backfill_batch result={result}", log_to_console)
    return result


@frappe.whitelist()
def run_backfill_until_done(
    legacy_batch_size: int = 5000,
    normalize_batch_size: int = 5000,
    group_batch_size: int = 500,
    max_batches: int = 200,
    sleep_seconds: float = 1,
    log_records: bool = False,
    log_to_console: bool = True,
):
    require_dedupe_manager()
    max_batches = max(1, int(max_batches or 200))
    sleep_seconds = max(0, float(sleep_seconds or 0))
    log_records = _as_bool(log_records)

    _log_backfill(
        "backfill_until_done started "
        f"legacy_batch_size={legacy_batch_size} normalize_batch_size={normalize_batch_size} "
        f"group_batch_size={group_batch_size} max_batches={max_batches} "
        f"sleep_seconds={sleep_seconds} log_records={log_records}",
        log_to_console,
    )

    summary = {
        "batches": 0,
        "legacy_processed": 0,
        "normalized_processed": 0,
        "normalized_updated": 0,
        "groups_processed": 0,
        "done": False,
        "last_result": None,
    }

    for batch_no in range(max_batches):
        result = run_backfill_batch(
            legacy_batch_size=legacy_batch_size,
            normalize_batch_size=normalize_batch_size,
            group_batch_size=group_batch_size,
            log_records=log_records,
            log_to_console=log_to_console,
        )

        summary["batches"] = batch_no + 1
        summary["last_result"] = result
        summary["legacy_processed"] += int(result.get("legacy", {}).get("processed") or 0)
        summary["normalized_processed"] += int(result.get("normalize", {}).get("processed") or 0)
        summary["normalized_updated"] += int(result.get("normalize", {}).get("updated") or 0)
        summary["groups_processed"] += int(result.get("groups", {}).get("processed") or 0)
        summary["done"] = bool(result.get("done"))
        _log_backfill(
            f"backfill_until_done batch={batch_no + 1}/{max_batches} summary={summary}",
            log_to_console,
        )

        if summary["done"]:
            break

        if sleep_seconds and batch_no + 1 < max_batches:
            time.sleep(sleep_seconds)

    _log_backfill(f"backfill_until_done finished summary={summary}", log_to_console)
    return summary


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

