# apps/crm_lead_dedupe/crm_lead_dedupe/install.py
from crm_lead_dedupe.logging import log_operation
from crm_lead_dedupe.settings import ensure_settings_defaults
from .setup.crm_lead_cf import apply as apply_crm_lead_cf

def after_install():
    log_operation("after_install.start")
    # Keep install fast on sites with large CRM Lead tables. Historical lead
    # backfill can be run explicitly after install during a maintenance window.
    result = apply_crm_lead_cf(run_backfill=False)
    settings_seeded = ensure_settings_defaults()
    log_operation("after_install.done", result=result, settings_seeded=settings_seeded)

def after_migrate():
    log_operation("after_migrate.start")
    # Ensure CFs/indexes exist after updates without reprocessing all old leads.
    result = apply_crm_lead_cf(run_backfill=False)
    settings_seeded = ensure_settings_defaults()
    log_operation("after_migrate.done", result=result, settings_seeded=settings_seeded)
