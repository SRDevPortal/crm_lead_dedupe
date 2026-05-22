# apps/crm_lead_dedupe/crm_lead_dedupe/install.py
from .setup.crm_lead_cf import apply as apply_crm_lead_cf

def after_install():
    # Keep install fast on sites with large CRM Lead tables. Historical lead
    # backfill can be run explicitly after install during a maintenance window.
    apply_crm_lead_cf(run_backfill=False)

def after_migrate():
    # Ensure CFs/indexes exist after updates without reprocessing all old leads.
    apply_crm_lead_cf(run_backfill=False)
