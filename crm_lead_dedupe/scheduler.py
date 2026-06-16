import frappe
from frappe.model.rename_doc import rename_doc
from frappe.utils import cint, get_datetime, now_datetime
from frappe.utils.file_lock import LockTimeoutError
from frappe.utils.synchronization import filelock

from crm_lead_dedupe.integrations.wa_chat_hub import relink_crm_lead_conversations
from crm_lead_dedupe.leads.dup_utils import (
    DT,
    DUPLICATE_OF_FIELD,
    GROUP_STATE_FIELDS,
    LEGACY_DUPLICATE_OF_FIELD,
    _lead_fields,
    duplicate_filters,
    is_valid_auto_merge_mobile,
    pipeline_scope_enabled,
    select_owner_source_row,
    select_primary_row,
    sync_duplicate_group,
)
from crm_lead_dedupe.logging import log_operation
from crm_lead_dedupe.settings import get_setting, is_enabled


AUTO_MERGE_LOG_DOCTYPE = "CRM Lead Auto Merge Log"
GLOBAL_LOCK = "crm_lead_dedupe_scheduler"
MOBILE_LOCK_PREFIX = "crm_lead_dedupe_mobile_"
HISTORICAL_PROGRESS_KEY = "crm_lead_dedupe_historical_last_mobile_norm"
SCHEDULER_LAST_RUN_KEY = "crm_lead_dedupe_scheduler_last_run"


def _setting_int(key: str, default: int, minimum: int = 1) -> int:
    try:
        value = cint(get_setting(key))
    except Exception:
        value = default
    return max(minimum, value or default)


def _blocked_mobiles() -> set[str]:
    value = get_setting("crm_lead_dedupe_blocked_mobiles") or ""
    if isinstance(value, str):
        return {line.strip() for line in value.splitlines() if line.strip()}
    if isinstance(value, (list, tuple, set)):
        return {str(item).strip() for item in value if str(item).strip()}
    return set()


def _has_required_columns() -> bool:
    required = ("sr_mobile_norm", "sr_dedupe_pending", "sr_dedupe_status")
    return all(frappe.db.has_column(DT, fieldname) for fieldname in required)


def _pending_mobile_groups(limit: int) -> list[frappe._dict]:
    if pipeline_scope_enabled():
        rows = frappe.db.sql(
            f"""
            select sr_mobile_norm, sr_lead_pipeline, min(modified) as oldest_modified
            from `tab{DT}`
            where sr_dedupe_pending = 1
                and ifnull(sr_mobile_norm, '') != ''
            group by sr_mobile_norm, sr_lead_pipeline
            order by oldest_modified asc
            limit %(limit)s
            """,
            {"limit": limit},
            as_dict=True,
        )
        return rows

    rows = frappe.db.sql(
        f"""
        select distinct sr_mobile_norm, null as sr_lead_pipeline
        from `tab{DT}`
        where sr_dedupe_pending = 1
            and ifnull(sr_mobile_norm, '') != ''
        order by modified asc
        limit %(limit)s
        """,
        {"limit": limit},
        as_dict=True,
    )
    return rows


@frappe.whitelist()
def queue_historical_duplicate_groups(batch_size: int = 500, reset: bool = False):
    """Mark old duplicate mobile groups pending so the 5-minute scheduler can merge them safely."""
    if not is_enabled("scheduler") or not _has_required_columns():
        return {"queued_groups": 0, "done": True, "skipped": "disabled_or_missing_columns"}

    if reset:
        frappe.defaults.set_global_default(HISTORICAL_PROGRESS_KEY, "")

    batch_size = max(1, cint(batch_size) or 500)
    last_mobile_norm = frappe.defaults.get_global_default(HISTORICAL_PROGRESS_KEY) or ""
    blocked = _blocked_mobiles()
    if pipeline_scope_enabled():
        rows = frappe.db.sql(
            f"""
            select sr_mobile_norm, sr_lead_pipeline, count(*) as total
            from `tab{DT}`
            where ifnull(sr_mobile_norm, '') != ''
                and sr_mobile_norm > %(last_mobile_norm)s
            group by sr_mobile_norm, sr_lead_pipeline
            having count(*) > 1
            order by sr_mobile_norm asc
            limit %(batch_size)s
            """,
            {"last_mobile_norm": last_mobile_norm, "batch_size": batch_size},
            as_dict=True,
        )
    else:
        rows = frappe.db.sql(
            f"""
            select sr_mobile_norm, null as sr_lead_pipeline, count(*) as total
            from `tab{DT}`
            where ifnull(sr_mobile_norm, '') != ''
                and sr_mobile_norm > %(last_mobile_norm)s
            group by sr_mobile_norm
            having count(*) > 1
            order by sr_mobile_norm asc
            limit %(batch_size)s
            """,
            {"last_mobile_norm": last_mobile_norm, "batch_size": batch_size},
            as_dict=True,
        )

    if not rows:
        return {"queued_groups": 0, "last_mobile_norm": last_mobile_norm, "done": True}

    queued_groups = 0
    for row in rows:
        mobile_norm = row.sr_mobile_norm
        status = "Pending" if is_valid_auto_merge_mobile(mobile_norm, blocked) else "Skipped"
        pending = 1 if status == "Pending" else 0
        _set_group_status(
            mobile_norm,
            row.get("sr_lead_pipeline"),
            status,
            None if pending else "Unsafe or invalid mobile number",
            pending=pending,
        )
        queued_groups += pending

    last_mobile_norm = rows[-1].sr_mobile_norm
    frappe.defaults.set_global_default(HISTORICAL_PROGRESS_KEY, last_mobile_norm)
    frappe.db.commit()
    return {
        "queued_groups": queued_groups,
        "processed_groups": len(rows),
        "last_mobile_norm": last_mobile_norm,
        "done": len(rows) < batch_size,
    }


def _group_rows(mobile_norm: str, pipeline: str | None = None):
    return frappe.get_all(
        DT,
        filters=duplicate_filters(mobile_norm, pipeline),
        fields=_lead_fields(["sr_mobile_norm", *GROUP_STATE_FIELDS]),
        order_by="creation desc",
        limit_page_length=0,
    )


def _set_group_status(mobile_norm: str, pipeline: str | None, status: str, error: str | None = None, pending: int = 0):
    values = {
        "sr_dedupe_pending": pending,
        "sr_dedupe_status": status,
        "sr_dedupe_checked_on": now_datetime(),
    }
    if frappe.db.has_column(DT, "sr_dedupe_error"):
        values["sr_dedupe_error"] = error
    names = frappe.get_all(DT, filters=duplicate_filters(mobile_norm, pipeline), pluck="name", limit_page_length=0)
    if names:
        frappe.db.bulk_update(DT, {name: values for name in names}, update_modified=False)


def _write_merge_log(mobile_norm: str, master: str | None, duplicate: str | None, status: str, error: str | None = None):
    log_operation(
        "auto_merge.log",
        mobile_norm=mobile_norm,
        master=master,
        duplicate=duplicate,
        status=status,
        error=error,
    )
    if not frappe.db.exists("DocType", AUTO_MERGE_LOG_DOCTYPE):
        return
    try:
        frappe.get_doc(
            {
                "doctype": AUTO_MERGE_LOG_DOCTYPE,
                "mobile_norm": mobile_norm,
                "master_lead": master,
                "duplicate_lead": duplicate,
                "status": status,
                "error": error,
            }
        ).insert(ignore_permissions=True)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "CRM Lead Auto Merge Log Failed")


def _owner_values_from_row(row) -> dict:
    values = {}
    if not row:
        return values

    if frappe.db.has_column(DT, "lead_owner"):
        values["lead_owner"] = row.get("lead_owner")

    assigned = row.get("_assign")
    if assigned:
        if isinstance(assigned, list):
            values["_assign"] = frappe.as_json(assigned)
        else:
            values["_assign"] = assigned
    elif row.get("lead_owner"):
        values["_assign"] = frappe.as_json([row.get("lead_owner")])
    else:
        values["_assign"] = "[]"

    return values


def _restore_owner_values(master: str, values: dict):
    if not values or not frappe.db.exists(DT, master):
        return

    frappe.db.set_value(DT, master, values, update_modified=False)


def _merge_duplicate(master: str, duplicate: str, mobile_norm: str):
    if not frappe.db.exists(DT, master) or not frappe.db.exists(DT, duplicate):
        _write_merge_log(mobile_norm, master, duplicate, "Skipped", "Master or duplicate no longer exists")
        return False

    relink_crm_lead_conversations(master, [duplicate])
    rename_doc(DT, duplicate, master, force=True, merge=True, ignore_permissions=True)

    values = {
        "sr_is_duplicate": 0,
        DUPLICATE_OF_FIELD: None,
        "sr_duplicate_score": 0,
        "sr_dedupe_pending": 0,
        "sr_dedupe_status": "Master",
        "sr_dedupe_checked_on": now_datetime(),
    }
    if frappe.db.has_column(DT, LEGACY_DUPLICATE_OF_FIELD):
        values[LEGACY_DUPLICATE_OF_FIELD] = None
    if frappe.db.has_column(DT, "sr_dedupe_error"):
        values["sr_dedupe_error"] = None
    frappe.db.set_value(DT, master, values, update_modified=False)
    _write_merge_log(mobile_norm, master, duplicate, "Merged")
    return True


def process_mobile_group(mobile_norm: str, max_merges: int, max_group_size: int, pipeline: str | None = None) -> int:
    blocked = _blocked_mobiles()
    if not is_valid_auto_merge_mobile(mobile_norm, blocked):
        _set_group_status(mobile_norm, pipeline, "Skipped", "Unsafe or invalid mobile number")
        _write_merge_log(mobile_norm, None, None, "Skipped", "Unsafe or invalid mobile number")
        frappe.db.commit()
        return 0

    lock_name = f"{MOBILE_LOCK_PREFIX}{mobile_norm}_{pipeline or ''}"
    with filelock(lock_name, timeout=0):
        rows = _group_rows(mobile_norm, pipeline)
        if len(rows) <= 1:
            _set_group_status(mobile_norm, pipeline, "Master")
            frappe.db.commit()
            return 0

        if len(rows) > max_group_size:
            message = f"Group size {len(rows)} exceeds limit {max_group_size}"
            _set_group_status(mobile_norm, pipeline, "Skipped", message)
            _write_merge_log(mobile_norm, None, None, "Skipped", message)
            frappe.db.commit()
            return 0

        primary = select_primary_row(rows)
        if not primary:
            _set_group_status(mobile_norm, pipeline, "Skipped", "No primary could be selected")
            frappe.db.commit()
            return 0

        master = primary.name
        owner_values = _owner_values_from_row(select_owner_source_row(rows))
        merged = 0
        for row in rows:
            if row.name == master:
                continue
            if merged >= max_merges:
                break

            try:
                frappe.flags.crm_lead_dedupe_scheduler = True
                if _merge_duplicate(master, row.name, mobile_norm):
                    merged += 1
                    frappe.db.commit()
            except Exception as exc:
                frappe.db.rollback()
                error = str(exc)[:1000]
                if frappe.db.exists(DT, row.name):
                    values = {
                        "sr_dedupe_pending": 0,
                        "sr_dedupe_status": "Failed",
                        "sr_dedupe_checked_on": now_datetime(),
                    }
                    if frappe.db.has_column(DT, "sr_dedupe_error"):
                        values["sr_dedupe_error"] = error
                    frappe.db.set_value(
                        DT,
                        row.name,
                        values,
                        update_modified=False,
                    )
                    frappe.db.commit()
                _write_merge_log(mobile_norm, master, row.name, "Failed", error)
                frappe.log_error(frappe.get_traceback(), "CRM Lead Auto Merge Failed")
            finally:
                frappe.flags.crm_lead_dedupe_scheduler = False

        try:
            _restore_owner_values(master, owner_values)
            sync_duplicate_group(mobile_norm, pipeline)
            _restore_owner_values(master, owner_values)
            _set_group_status(mobile_norm, pipeline, "Master")
            frappe.db.commit()
        except Exception:
            frappe.db.rollback()
            frappe.log_error(frappe.get_traceback(), "CRM Lead Group Sync After Auto Merge Failed")

        return merged


def run_auto_merge_scheduler():
    if not is_enabled("scheduler") or not is_enabled("merge"):
        log_operation("auto_merge_scheduler.skipped", reason="disabled")
        return {"processed_groups": 0, "merged": 0, "skipped": "disabled"}

    if not _has_required_columns():
        log_operation("auto_merge_scheduler.skipped", reason="missing_columns")
        return {"processed_groups": 0, "merged": 0, "skipped": "missing_columns"}

    max_pending = _setting_int("crm_lead_dedupe_max_pending_leads", 2000)
    max_groups = _setting_int("crm_lead_dedupe_max_mobile_groups", 500)
    max_merges = _setting_int("crm_lead_dedupe_max_merges_per_run", 100)
    max_group_size = _setting_int("crm_lead_dedupe_max_group_size", 100)
    limit = min(max_pending, max_groups)

    try:
        with filelock(GLOBAL_LOCK, timeout=0):
            mobile_groups = _pending_mobile_groups(limit)
            processed_groups = 0
            merged = 0

            log_operation("auto_merge_scheduler.start", group_count=len(mobile_groups), max_merges=max_merges)
            for group in mobile_groups:
                if merged >= max_merges:
                    break
                mobile_norm = group.sr_mobile_norm
                pipeline = group.get("sr_lead_pipeline")
                try:
                    merged += process_mobile_group(mobile_norm, max_merges - merged, max_group_size, pipeline)
                    processed_groups += 1
                except LockTimeoutError:
                    log_operation("auto_merge_scheduler.group_locked", mobile_norm=mobile_norm)
                except Exception:
                    frappe.db.rollback()
                    _set_group_status(mobile_norm, pipeline, "Failed", frappe.get_traceback()[:1000])
                    frappe.db.commit()
                    frappe.log_error(frappe.get_traceback(), "CRM Lead Auto Merge Group Failed")

            result = {"processed_groups": processed_groups, "merged": merged}
            log_operation("auto_merge_scheduler.done", **result)
            return result
    except LockTimeoutError:
        log_operation("auto_merge_scheduler.skipped", reason="already_running")
        return {"processed_groups": 0, "merged": 0, "skipped": "already_running"}


def run_auto_merge_scheduler_if_due():
    interval_minutes = _setting_int("crm_lead_dedupe_scheduler_interval_minutes", 5)
    now = now_datetime()
    last_run = frappe.defaults.get_global_default(SCHEDULER_LAST_RUN_KEY)

    if last_run:
        try:
            elapsed_seconds = (now - get_datetime(last_run)).total_seconds()
            if elapsed_seconds < interval_minutes * 60:
                log_operation(
                    "auto_merge_scheduler.skipped",
                    reason="interval_not_due",
                    interval_minutes=interval_minutes,
                )
                return {"processed_groups": 0, "merged": 0, "skipped": "interval_not_due"}
        except Exception:
            pass

    frappe.defaults.set_global_default(SCHEDULER_LAST_RUN_KEY, now)
    frappe.db.commit()
    return run_auto_merge_scheduler()
