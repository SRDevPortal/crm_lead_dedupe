# apps/crm_lead_dedupe/crm_lead_dedupe/install.py
from .setup.crm_lead_cf import apply as apply_crm_lead_cf

def after_install():
    # ensure CFs are created on first install
    apply_crm_lead_cf()

def after_migrate():
    # ensure CFs exist after updates, and re-run any idempotent setup
    apply_crm_lead_cf()
