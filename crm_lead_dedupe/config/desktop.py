from frappe import _


def get_data():
    return [
        {
            "module_name": "CRM Lead Dedupe",
            "type": "module",
            "label": _("CRM Lead Dedupe"),
            "color": "blue",
            "icon": "octicon octicon-git-merge",
            "description": _("Duplicate detection and merge controls for CRM Leads"),
        }
    ]
