import frappe
from crm.api.doc import get_data as crm_get_data


ACTIVE_FILTERS = {"sr_is_archived": 0, "converted": 0}


def _as_filter_dict(value):
    if not value:
        return {}

    parsed = frappe.parse_json(value) if isinstance(value, str) else value
    if not isinstance(parsed, dict):
        return {}

    return dict(parsed)


def force_active_crm_lead_filters(doctype, filters=None, default_filters=None):
    if doctype != "CRM Lead":
        return filters, default_filters

    filters = _as_filter_dict(filters)
    default_filters = _as_filter_dict(default_filters)

    filters.update(ACTIVE_FILTERS)
    default_filters.update(ACTIVE_FILTERS)
    return filters, default_filters


@frappe.whitelist()
def get_data(
    doctype: str,
    filters: dict,
    order_by: str,
    page_length=20,
    page_length_count=20,
    column_field=None,
    title_field=None,
    columns=None,
    rows=None,
    kanban_columns=None,
    kanban_fields=None,
    view=None,
    default_filters=None,
):
    filters, default_filters = force_active_crm_lead_filters(
        doctype,
        filters,
        default_filters,
    )
    return crm_get_data(
        doctype=doctype,
        filters=filters,
        order_by=order_by,
        page_length=page_length,
        page_length_count=page_length_count,
        column_field=column_field,
        title_field=title_field,
        columns=columns or [],
        rows=rows or [],
        kanban_columns=kanban_columns or [],
        kanban_fields=kanban_fields or [],
        view=view,
        default_filters=default_filters,
    )
