import frappe


def _has_chat_conversation() -> bool:
    return frappe.db.exists("DocType", "Chat Conversation")


def _chat_meta_has(fieldname: str) -> bool:
    return frappe.get_meta("Chat Conversation").has_field(fieldname)


def relink_crm_lead_conversations(primary: str, duplicates) -> dict:
    """Move WA Chat Hub conversation links from duplicate CRM Leads to primary."""
    duplicate_names = _as_list(duplicates)
    if not primary or not duplicate_names or not _has_chat_conversation():
        return {"updated": 0}

    filters = []
    if _chat_meta_has("linked_crm_lead"):
        filters.append({"linked_crm_lead": ["in", duplicate_names]})
    if _chat_meta_has("linked_reference_doctype") and _chat_meta_has("linked_reference_name"):
        filters.append(
            {
                "linked_reference_doctype": ["in", ["CRM Lead", "Lead"]],
                "linked_reference_name": ["in", duplicate_names],
            }
        )

    if not filters:
        return {"updated": 0}

    names = set()
    for row_filter in filters:
        for name in frappe.get_all("Chat Conversation", filters=row_filter, pluck="name", limit_page_length=0):
            names.add(name)

    values = {}
    if _chat_meta_has("linked_crm_lead"):
        values["linked_crm_lead"] = primary
    if _chat_meta_has("linked_reference_doctype"):
        values["linked_reference_doctype"] = "CRM Lead"
    if _chat_meta_has("linked_reference_name"):
        values["linked_reference_name"] = primary

    for name in names:
        frappe.db.set_value("Chat Conversation", name, values, update_modified=False)

    contact_updates = _relink_chat_contacts(primary, duplicate_names)
    return {"updated": len(names), "contacts_updated": contact_updates}


def _relink_chat_contacts(primary: str, duplicate_names: list[str]) -> int:
    if not frappe.db.exists("DocType", "Chat Contact"):
        return 0

    meta = frappe.get_meta("Chat Contact")
    if not meta.has_field("source_doctype") or not meta.has_field("source_name"):
        return 0

    names = frappe.get_all(
        "Chat Contact",
        filters={
            "source_doctype": ["in", ["CRM Lead", "Lead"]],
            "source_name": ["in", duplicate_names],
        },
        pluck="name",
        limit_page_length=0,
    )
    if not names:
        return 0

    for name in names:
        frappe.db.set_value(
            "Chat Contact",
            name,
            {"source_doctype": "CRM Lead", "source_name": primary},
            update_modified=False,
        )
    return len(names)


def _as_list(value) -> list[str]:
    if isinstance(value, str):
        try:
            value = frappe.parse_json(value)
        except Exception:
            value = [value]
    if not isinstance(value, list):
        return []
    return [item.get("name") if isinstance(item, dict) else item for item in value if item]
