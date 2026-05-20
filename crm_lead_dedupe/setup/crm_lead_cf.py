# apps/crm_lead_dedupe/crm_lead_dedupe/setup/crm_lead_cf.py
import frappe
DT = "CRM Lead"

def apply():
    if not frappe.db.exists("DocType", DT):
        return

    def add_cf(df):
        if not frappe.db.exists("Custom Field", {"dt": DT, "fieldname": df["fieldname"]}):
            cf = frappe.get_doc({"doctype": "Custom Field", "dt": DT, **df})
            cf.insert(ignore_permissions=True)

    for df in [
        # Dedupe
        {"fieldname": "sr_dedupe_tab","label":"Duplicates","fieldtype":"Tab Break","insert_after":"sr_w_team_id"},
        {"fieldname": "sr_dedupe_sec","label":"","fieldtype":"Section Break","insert_after":"sr_dedupe_tab"},

        {"fieldname":"sr_mobile_norm","label":"Mobile (Normalized)","fieldtype":"Data","insert_after":"sr_dedupe_sec","hidden":1,"read_only":1},
        {"fieldname":"sr_duplicate_of","label":"Duplicate Of","fieldtype":"Link","options":"CRM Lead","insert_after":"sr_mobile_norm","hidden":1,"read_only":1},
        {"fieldname":"sr_duplicate_score","label":"Duplicate Score","fieldtype":"Float","insert_after":"sr_duplicate_of","default":0,"hidden":1,"read_only":1},
        {"fieldname":"sr_is_duplicate","label":"Is Duplicate","fieldtype":"Check","insert_after":"sr_duplicate_score","hidden":1,"default":0},
        {"fieldname":"sr_dup_candidates_json","label":"Dup Candidates (JSON)","fieldtype":"Small Text","insert_after":"sr_is_duplicate","hidden":1},
        {"fieldname":"sr_dup_hit_count","label":"Dup Hit Count","fieldtype":"Int","insert_after":"sr_dup_candidates_json","default":0,"hidden":1},
        {"fieldname": "sr_is_archived","label":"Archived (Hidden)","fieldtype":"Check","default":"0","insert_after":"sr_dup_hit_count","in_list_view":0,"in_standard_filter":0,"read_only":1},
    ]:
        add_cf(df)

