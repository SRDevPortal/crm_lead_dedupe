import frappe
from frappe import _

ARCHIVE_VIEW_ROLES = {"System Manager", "CRM Manager", "Sales Manager"}
DEDUPE_MANAGER_ROLES = ARCHIVE_VIEW_ROLES
COLUMN_CUSTOMIZER_ROLES = {"System Manager", "Administrator"}
ACTIVE_LEAD_CONDITION = (
    "coalesce(`tabCRM Lead`.`sr_is_archived`, 0) = 0 "
    "and coalesce(`tabCRM Lead`.`converted`, 0) = 0"
)


def _session_user(user: str | None = None) -> str:
    return user or frappe.session.user


def has_role(user: str | None, roles: set[str]) -> bool:
    user = _session_user(user)
    if user == "Administrator":
        return True
    return bool(roles.intersection(frappe.get_roles(user)))


def can_view_archived(user: str | None = None) -> bool:
    return has_role(user, ARCHIVE_VIEW_ROLES)


def can_manage_dedupe(user: str | None = None) -> bool:
    return has_role(user, DEDUPE_MANAGER_ROLES)


def can_customize_modal_columns(user: str | None = None) -> bool:
    return has_role(user, COLUMN_CUSTOMIZER_ROLES)


def require_dedupe_manager(user: str | None = None):
    if not can_manage_dedupe(user):
        frappe.throw(
            _("Only CRM managers can manage duplicate leads."),
            frappe.PermissionError,
        )


def require_lead_read(name: str, user: str | None = None):
    if not name or not frappe.db.exists("CRM Lead", name):
        frappe.throw(_("CRM Lead {0} does not exist.").format(name), frappe.DoesNotExistError)
    if not frappe.has_permission("CRM Lead", "read", name, user=_session_user(user)):
        frappe.throw(_("Not permitted to read CRM Lead {0}.").format(name), frappe.PermissionError)


def pqc_crm_lead(user, doctype=None):
    # Normal list/report queries should stay active-only. Manager-only archive
    # actions use direct permission checks and dedicated APIs when needed.
    return ACTIVE_LEAD_CONDITION


def crm_lead_has_permission(doc, ptype, user):
    if can_view_archived(user):
        return None

    if doc.get("sr_is_archived") or doc.get("converted"):
        if ptype in ("read", "print", "report", "write", "delete", "share", "email"):
            return False
        return False
    return None
