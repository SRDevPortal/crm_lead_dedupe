# CRM Lead Dedupe Operational Guide

This app is designed for high-volume CRM Lead dedupe where the business rule is:

```text
If the last 10 digits of the mobile number match, auto-merge the duplicate CRM Lead.
```

The system must never compare every lead with every other lead. With lakhs of leads, that pattern can overload MariaDB, Frappe workers, and the ERPNext server.

## Non-Negotiable Rules

1. Do not scan all CRM Leads every 5 minutes.
2. Do not merge inside the user-facing Lead save request.
3. Do not use `RIGHT(mobile_no, 10)` or other functions in lookup filters for production dedupe.
4. Always normalize mobile once into `sr_mobile_norm`.
5. Always query by indexed `sr_mobile_norm`.
6. Always process duplicate groups in batches.
7. Always keep scheduler and merge kill switches available.
8. Always keep audit logs for automatic merges.

## Correct Runtime Flow

```text
CRM Lead save
  -> normalize mobile_no into sr_mobile_norm
  -> mark sr_dedupe_pending = 1
  -> finish save quickly

5-minute scheduler
  -> fetch pending mobile groups
  -> lock one mobile group
  -> re-fetch all leads for that mobile
  -> select one master
  -> merge duplicates into master through Frappe merge logic
  -> write CRM Lead Auto Merge Log
  -> clear pending status
```

## Required Indexes

The following indexes must exist on `tabCRM Lead`:

```text
sr_mobile_norm
(sr_mobile_norm, creation)
(sr_mobile_norm, sr_is_archived, converted, creation)
(sr_dedupe_pending, modified)
(sr_is_archived, converted, modified)
```

If WA Chat Hub relinking is enabled, these indexes must also exist:

```text
tabChat Conversation: linked_crm_lead
tabChat Conversation: linked_reference_doctype, linked_reference_name
tabChat Contact: source_doctype, source_name
```

## Scheduler Limits

Keep these limits conservative in production:

```text
Max Pending Leads Per Run: 2000
Max Mobile Groups Per Run: 500
Max Merges Per Run: 100
Max Group Size: 100
```

Increase limits only after checking CPU, DB load, slow queries, and merge failure rate.

## Race Conditions

If 50-60 leads are added at once with the same mobile number:

```text
All leads are marked Pending.
Scheduler extracts the mobile number once.
Mobile-level lock is acquired.
All leads in that mobile group are re-fetched.
One master is selected.
Duplicates are merged sequentially.
```

This avoids 50-60 separate merge jobs racing against each other.

The scheduler also uses a global lock so overlapping scheduler runs do not process the same work twice.

## Unsafe Mobile Numbers

Never auto-merge blank, short, dummy, or common mobile numbers.

Examples:

```text
0000000000
1111111111
2222222222
3333333333
4444444444
5555555555
6666666666
7777777777
8888888888
9999999999
1234567890
```

Mobile numbers must be exactly 10 digits after normalization.

## Historical Cleanup

Do not process all historical leads directly through the 5-minute scheduler.

Use the historical queue helper during off-hours:

```bash
bench --site <site-name> execute crm_lead_dedupe.scheduler.queue_historical_duplicate_groups --kwargs "{'batch_size': 500}"
```

This marks old duplicate mobile groups as pending. The normal scheduler then merges them safely within configured limits.

## Emergency Stop

Use these settings as kill switches:

```text
Enable CRM Lead Dedupe
Enable Scheduler
Enable Merge
Enable Save Hooks
```

If server load rises unexpectedly, first disable:

```text
Enable Scheduler
Enable Merge
```

Existing Lead saves will remain safer than running merge workloads.

## Deployment Checklist

Before enabling production auto-merge:

1. Take a full database backup.
2. Run migration.
3. Confirm indexes exist.
4. Run smoke test with two test leads.
5. Enable scheduler with low merge limits.
6. Monitor CPU, MariaDB load, slow queries, and error logs.
7. Run historical cleanup only during off-hours.

## Verification Commands

Run tests:

```bash
bench --site <site-name> run-tests --app crm_lead_dedupe
```

Run scheduler manually:

```bash
bench --site <site-name> execute crm_lead_dedupe.scheduler.run_auto_merge_scheduler
```

Queue historical duplicate groups:

```bash
bench --site <site-name> execute crm_lead_dedupe.scheduler.queue_historical_duplicate_groups --kwargs "{'batch_size': 500}"
```

## What Caused The Original Risk

The dangerous pattern is repeated full-table dedupe work:

```text
for each Lead:
  search or compare against many/all previous Leads
```

At 6 lakh records, this can become extremely expensive. The safe pattern is:

```text
normalize -> indexed mobile lookup -> locked group merge -> audit
```

