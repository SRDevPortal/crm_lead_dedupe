// apps/crm_lead_dedupe/crm_lead_dedupe/public/js/crm_lead_modal.js

// ---------- helpers ----------
function _ld_esc(t, fallback = "-") {
  const value = (t === undefined || t === null || t === "") ? fallback : t;
  return frappe.utils.escape_html(String(value)).replace(/\n/g, "<br>");
}
function _ld_clean(t) {
  return (t || "").replace(/<[^>]*>/g, "").replace(/&nbsp;/g, " ").trim();
}
function _ld_css_block() {
  return `
  <style>
    .modal-dialog.ld-full-modal { width: min(1480px, calc(100vw - 96px)); max-width: none; margin: 48px auto; }
    .modal-dialog.ld-full-modal .modal-content { height: auto; max-height: calc(100vh - 96px); display: flex; flex-direction: column; }
    .modal-dialog.ld-full-modal .modal-body { flex: 1; min-height: 0; overflow: hidden; padding: 0; }
    .ld-wrap { height: calc(100vh - 170px); min-height: 420px; display: flex; flex-direction: column; padding: 16px; }
    .ld-head { flex: 0 0 auto; }
    .ld-head { margin: 0 0 10px; padding: 0 0 8px; border-bottom: 1px solid #eee; }
    .ld-head-row { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
    .ld-head-actions { flex: 0 0 auto; display: flex; gap: 8px; }
    .ld-muted { color: #666; }
    .ld-table-zone { flex: 1 1 auto; min-height: 0; display: flex; overflow: hidden; }
    .ld-table-wrap { flex: 1 1 auto; min-height: 0; max-width: 100%; overflow: auto; overscroll-behavior: contain; border: 1px solid #eee; border-radius: 6px; }
    .ld-table { width: max-content; min-width: 100%; border-collapse: separate; border-spacing: 0; }
    .ld-table th, .ld-table td { box-sizing: border-box; min-width: 140px; padding: 8px 10px; border-bottom: 1px solid #f0f0f0; vertical-align: top; white-space: nowrap; background: #fff; }
    .ld-table th { font-weight: 600; position: sticky; top: 0; z-index: 2; }
    .ld-table tbody tr:hover td { background: #fafafa; }
    .ld-col-check { width: 44px; min-width: 44px; max-width: 44px; text-align: center; }
    .ld-col-id { min-width: 190px; }
    .ld-col-date { min-width: 170px; }
    .ld-col-mobile { min-width: 130px; }
    .ld-col-name { min-width: 220px; max-width: 340px; white-space: normal; }
    .ld-col-score { width: 84px; min-width: 84px; text-align: right; }
    .ld-sticky-check { position: sticky; left: 0; z-index: 3; box-shadow: 1px 0 0 #eee; }
    .ld-sticky-id { position: sticky; left: 44px; z-index: 3; box-shadow: 1px 0 0 #eee; }
    .ld-table th.ld-sticky-check, .ld-table th.ld-sticky-id { z-index: 4; }
    .ld-badge { display: inline-block; padding: 2px 8px; border-radius: 999px; background: #eef3ff; border: 1px solid #dbe3ff; }
    .ld-actions { flex: 0 0 auto; background: #fff; padding: 10px 0 0; border-top: 1px solid #eee; display: flex; gap: 8px; justify-content: flex-end; align-items: center; }
    .ld-row-subtle { color: #444; font-size: 12px; }
    .ld-col-picker { max-height: min(560px, calc(100vh - 240px)); overflow: auto; padding-right: 4px; }
    .ld-col-picker-row { display: grid; grid-template-columns: minmax(190px, 1fr) auto auto; align-items: center; gap: 8px; padding: 8px 0; border-bottom: 1px solid #f0f0f0; }
    .ld-col-picker-row label { margin: 0; display: inline-flex; align-items: center; gap: 8px; font-weight: 400; }
    .ld-col-picker-actions { display: inline-flex; gap: 4px; }
    .ld-col-picker-actions .btn { min-width: 48px; }
    @media (max-width: 768px) {
      .modal-dialog.ld-full-modal { width: 100vw; height: 100vh; margin: 0; }
      .modal-dialog.ld-full-modal .modal-content { height: 100vh; border-radius: 0; }
      .ld-wrap { height: calc(100vh - 58px); min-height: 0; padding: 12px; }
      .ld-head-row { flex-direction: column; }
    }
    @media print {
      .ld-actions { display:none !important; }
    }
  </style>`;
}

const LD_COLUMN_STORAGE_KEY = "crm_lead_dedupe.merged_records.columns.v1";

const LD_COLUMNS = [
  {
    key: "_select",
    label: "",
    className: "ld-col-check ld-sticky-check",
    internal: true,
    locked: true,
    cell: (row, _idx, context) => (
      `<input type="checkbox" class="ld-check" ${context.checkedNames.has(row.name) ? "checked" : ""}/>`
    ),
  },
  {
    key: "name",
    label: "Lead Id",
    className: "ld-col-id ld-sticky-id",
    locked: true,
    defaultVisible: true,
    cell: (row, _idx, context) => (
      `<a class="bold" href="/app/${context.doctypeSlug}/${_ld_esc(row.name, "")}" target="_blank">${_ld_esc(row.name)}</a>`
    ),
  },
  { key: "owner", label: "Owner", className: "ld-col-owner", defaultVisible: true, cell: row => _ld_esc(row.owner) },
  { key: "stage", label: "Stage", className: "ld-col-stage", defaultVisible: true, cell: row => `<span class="ld-badge">${_ld_esc(row.stage)}</span>` },
  {
    key: "creation",
    label: "Creation",
    className: "ld-col-date",
    defaultVisible: true,
    cell: row => _ld_esc(row.creation ? frappe.datetime.str_to_user(row.creation) : null),
  },
  { key: "mobile_no", label: "Mobile", className: "ld-col-mobile", defaultVisible: true, cell: row => _ld_esc(row.mobile_no) },
  { key: "lead_name", label: "Full Name", className: "ld-col-name", defaultVisible: true, cell: row => _ld_esc(row.lead_name) },
  { key: "platform", label: "Platform", className: "ld-col-platform", defaultVisible: true, cell: row => _ld_esc(row.platform) },
  { key: "source", label: "Source", className: "ld-col-source", defaultVisible: true, cell: row => _ld_esc(row.source) },
  { key: "score", label: "Score", className: "ld-col-score", defaultVisible: true, cell: row => _ld_esc(row.score) },
  { key: "pipeline", label: "Pipeline", className: "ld-col-pipeline", cell: row => _ld_esc(row.pipeline) },
  { key: "disposition", label: "Disposition", className: "ld-col-disposition", cell: row => _ld_esc(row.disposition) },
  { key: "team", label: "Sales Team", className: "ld-col-team", cell: row => _ld_esc(row.team) },
  { key: "lead_owner", label: "Lead Owner", className: "ld-col-lead-owner", cell: row => _ld_esc(row.lead_owner) },
  { key: "country", label: "Country", className: "ld-col-country", cell: row => _ld_esc(row.country) },
  { key: "email", label: "Email", className: "ld-col-email", cell: row => _ld_esc(row.email) },
  { key: "phone", label: "Phone", className: "ld-col-phone", cell: row => _ld_esc(row.phone) },
  { key: "lead_score", label: "Lead Score", className: "ld-col-lead-score", cell: row => _ld_esc(row.lead_score) },
  { key: "lead_temperature", label: "Temperature", className: "ld-col-temperature", cell: row => _ld_esc(row.lead_temperature) },
  { key: "landing_page", label: "Landing Page", className: "ld-col-landing", cell: row => _ld_esc(row.landing_page) },
  { key: "utm_source", label: "UTM Source", className: "ld-col-utm-source", cell: row => _ld_esc(row.utm_source) },
  { key: "utm_campaign", label: "UTM Campaign", className: "ld-col-utm-campaign", cell: row => _ld_esc(row.utm_campaign) },
  { key: "utm_medium", label: "UTM Medium", className: "ld-col-utm-medium", cell: row => _ld_esc(row.utm_medium) },
  { key: "utm_term", label: "UTM Term", className: "ld-col-utm-term", cell: row => _ld_esc(row.utm_term) },
  { key: "gclid", label: "GCLID", className: "ld-col-gclid", cell: row => _ld_esc(row.gclid) },
];

function _ld_backend_column_keys() {
  return LD_COLUMNS.filter(column => !column.internal).map(column => column.key);
}

function _ld_default_column_keys() {
  return LD_COLUMNS
    .filter(column => !column.internal && column.defaultVisible)
    .map(column => column.key);
}

function _ld_normalize_column_keys(keys) {
  const allowed = new Set(_ld_backend_column_keys());
  const lockedKeys = LD_COLUMNS
    .filter(column => column.locked && !column.internal)
    .map(column => column.key);
  const raw = Array.isArray(keys) ? keys : [];
  if (!raw.length) {
    return _ld_default_column_keys();
  }

  const normalized = [];

  raw.forEach(key => {
    if (allowed.has(key) && !normalized.includes(key)) {
      normalized.push(key);
    }
  });

  const unlocked = normalized.filter(key => !lockedKeys.includes(key));
  lockedKeys.forEach(key => {
    if (!unlocked.includes(key)) {
      unlocked.unshift(key);
    }
  });

  return unlocked.length ? unlocked : _ld_default_column_keys();
}

function _ld_can_customize_columns() {
  return frappe.session?.user === "Administrator"
    || frappe.user?.has_role?.(["System Manager", "Administrator"])
    || (frappe.user_roles || []).includes("System Manager")
    || (frappe.user_roles || []).includes("Administrator");
}

function _ld_load_column_keys() {
  try {
    const saved = window.localStorage && localStorage.getItem(LD_COLUMN_STORAGE_KEY);
    return _ld_normalize_column_keys(saved ? JSON.parse(saved) : _ld_default_column_keys());
  } catch (e) {
    return _ld_default_column_keys();
  }
}

function _ld_save_column_keys(keys) {
  const normalized = _ld_normalize_column_keys(keys);
  try {
    window.localStorage && localStorage.setItem(LD_COLUMN_STORAGE_KEY, JSON.stringify(normalized));
  } catch (e) {
    // Ignore private browsing/storage errors; the modal still works for this session.
  }
  return normalized;
}

function _ld_visible_columns(keys) {
  const selected = new Set(_ld_normalize_column_keys(keys));
  return LD_COLUMNS.filter(column => column.internal || selected.has(column.key));
}

function _ld_column_by_key(key) {
  return LD_COLUMNS.find(column => column.key === key);
}

function _ld_picker_column_order(columnKeys) {
  const order = [];
  _ld_normalize_column_keys(columnKeys).forEach(key => {
    if (!order.includes(key)) {
      order.push(key);
    }
  });
  _ld_backend_column_keys().forEach(key => {
    if (!order.includes(key)) {
      order.push(key);
    }
  });
  return order;
}

function _ld_col_attrs(column) {
  return column.className ? ` class="${column.className}"` : "";
}

function _ld_table_rows(rows, columns, checkedNames) {
  const doctypeSlug = (frappe.router && frappe.router.slug)
    ? frappe.router.slug('CRM Lead')
    : 'crm-lead';
  const context = { doctypeSlug, checkedNames };

  return rows.map((row, idx) => {
    const cells = columns.map(column => (
      `<td${_ld_col_attrs(column)}>${column.cell(row, idx, context)}</td>`
    )).join("");

    return `<tr data-name="${_ld_esc(row.name, "")}">${cells}</tr>`;
  }).join("");
}

function _ld_build_table(rows, columnKeys, checkedNames) {
  const columns = _ld_visible_columns(columnKeys);
  const headers = columns.map(column => (
    `<th${_ld_col_attrs(column)}>${_ld_esc(column.label, "")}</th>`
  )).join("");

  return `
    <div class="ld-table-wrap">
      <table class="ld-table">
        <thead>
          <tr>${headers}</tr>
        </thead>
        <tbody>${_ld_table_rows(rows, columns, checkedNames)}</tbody>
      </table>
    </div>
  `;
}

function _ld_checked_names($root, fallbackNames) {
  const names = Array.from($root.find('tbody .ld-check:checked').map((_, el) =>
    el.closest('tr').getAttribute('data-name')
  )).filter(Boolean);
  return new Set(names.length ? names : fallbackNames);
}

function _ld_open_columns_dialog(columnKeys, onApply) {
  const dialog = new frappe.ui.Dialog({
    title: "Merged record columns",
    fields: [
      {
        fieldtype: "HTML",
        fieldname: "columns_html",
        options: _ld_columns_dialog_html(columnKeys),
      },
    ],
  });

  dialog.set_primary_action("Apply", () => {
    const nextKeys = _ld_columns_from_dialog(dialog);
    onApply(_ld_save_column_keys(nextKeys));
    dialog.hide();
  });

  dialog.set_secondary_action(() => {
    const defaults = _ld_save_column_keys(_ld_default_column_keys());
    onApply(defaults);
    dialog.hide();
  });
  dialog.set_secondary_action_label("Reset Default");
  dialog.show();
  _ld_bind_columns_dialog(dialog);
}

function _ld_columns_dialog_html(columnKeys) {
  const selected = new Set(_ld_normalize_column_keys(columnKeys));
  const rows = _ld_picker_column_order(columnKeys).map(key => {
    const column = _ld_column_by_key(key);
    if (!column) return "";

    const locked = column.locked ? " data-locked=\"1\"" : "";
    const disabled = column.locked ? " disabled" : "";
    const checked = column.locked || selected.has(column.key) ? " checked" : "";
    const required = column.locked ? " <span class=\"text-muted\">(required)</span>" : "";

    return `
      <div class="ld-col-picker-row" data-key="${_ld_esc(column.key, "")}"${locked}>
        <label>
          <input type="checkbox" data-role="column-toggle"${checked}${disabled}>
          <span>${_ld_esc(column.label)}${required}</span>
        </label>
        <div class="ld-col-picker-actions">
          <button type="button" class="btn btn-xs btn-default" data-move="up">Up</button>
          <button type="button" class="btn btn-xs btn-default" data-move="down">Down</button>
        </div>
      </div>
    `;
  }).join("");

  return `<div class="ld-col-picker">${rows}</div>`;
}

function _ld_bind_columns_dialog(dialog) {
  const $root = dialog.$body.find(".ld-col-picker");

  function updateMoveButtons() {
    const $rows = $root.find(".ld-col-picker-row");
    $rows.each((idx, row) => {
      const $row = $(row);
      const locked = Boolean($row.data("locked"));
      const canMoveUp = !locked && idx > 1;
      const canMoveDown = !locked && idx < $rows.length - 1;

      $row.find('[data-move="up"]').prop("disabled", !canMoveUp);
      $row.find('[data-move="down"]').prop("disabled", !canMoveDown);
    });
  }

  $root.on("click", "[data-move]", (event) => {
    const $button = $(event.currentTarget);
    if ($button.prop("disabled")) return;

    const $row = $button.closest(".ld-col-picker-row");
    if ($row.data("locked")) return;

    if ($button.data("move") === "up") {
      const $prev = $row.prev(".ld-col-picker-row");
      if ($prev.length && !$prev.data("locked")) {
        $row.insertBefore($prev);
      }
    } else {
      const $next = $row.next(".ld-col-picker-row");
      if ($next.length) {
        $row.insertAfter($next);
      }
    }

    updateMoveButtons();
  });

  updateMoveButtons();
}

function _ld_columns_from_dialog(dialog) {
  const keys = [];
  dialog.$body.find(".ld-col-picker-row").each((_, row) => {
    const $row = $(row);
    const key = $row.attr("data-key");
    const checked = Boolean($row.data("locked"))
      || $row.find('[data-role="column-toggle"]').prop("checked");

    if (checked) {
      keys.push(key);
    }
  });
  return keys;
}

// ---------- main modal ----------
async function openCRMLeadDuplicatesDialog({ primary_name }) {
  try {
    const settings = (frappe.boot && frappe.boot.crm_lead_dedupe) || {};
    if (settings.enabled === false || settings.ui_enabled === false) {
      frappe.msgprint('CRM Lead Dedupe is disabled for this site.');
      return;
    }

    if (!primary_name) return;

    const d = new frappe.ui.Dialog({
      title: 'Merged records',
      size: 'large',
      static: true
    });

    const $dlg = d.$wrapper.find(".modal-dialog");
    $dlg.addClass("ld-full-modal");

    d.$body.html("<div style='padding:16px' class='text-muted'>Loading duplicates...</div>");
    d.show();

    const canCustomizeColumns = _ld_can_customize_columns();
    let selectedColumnKeys = canCustomizeColumns ? _ld_load_column_keys() : _ld_default_column_keys();
    const { message: rows = [] } = await frappe.call(
      'crm_lead_dedupe.api.crm_lead_duplicates.get_duplicates_for_crm_lead',
      {
        lead_name: primary_name,
        columns: canCustomizeColumns ? _ld_backend_column_keys() : _ld_default_column_keys(),
      }
    );
    frappe.call('crm_lead_dedupe.api.crm_lead_duplicates.acknowledge_duplicate_hit', {
      lead_name: primary_name,
    }).then(() => {
      if (frappe.listview_settings && window.cur_list && window.cur_list.doctype === 'CRM Lead') {
        window.cur_list.refresh();
      }
      if (window.cur_frm && window.cur_frm.doctype === 'CRM Lead' && window.cur_frm.doc && window.cur_frm.doc.name === primary_name) {
        window.cur_frm.reload_doc();
      }
    });
    let checkedNames = new Set(rows[0] && rows[0].name ? [rows[0].name] : []);

    function renderTable() {
      const $tableZone = d.$body.find('[data-role="table-zone"]');
      checkedNames = _ld_checked_names(d.$body, checkedNames);
      $tableZone.html(rows.length
        ? _ld_build_table(rows, selectedColumnKeys, checkedNames)
        : "<p class='ld-muted'>No duplicates found.</p>"
      );
    }

    const mergeEnabled = settings.merge_enabled !== false;
    const body = `
      ${_ld_css_block()}
      <div class="ld-wrap">
        <div class="ld-head">
          <div class="ld-head-row">
            <div>
              <div><b>Primary Lead:</b> ${_ld_esc(primary_name)}</div>
              <div class="ld-muted">${rows.length ? rows.length : 'No'} duplicate${rows.length===1?'':'s'} found by mobile.</div>
            </div>
            ${canCustomizeColumns ? `<div class="ld-head-actions">
              <button class="btn btn-default" data-action="columns">Columns</button>
            </div>` : ""}
          </div>
        </div>
        <div class="ld-table-zone" data-role="table-zone">
          ${rows.length ? _ld_build_table(rows, selectedColumnKeys, checkedNames) : "<p class='ld-muted'>No duplicates found.</p>"}
        </div>
        <div class="ld-actions">
          ${mergeEnabled ? '<button class="btn btn-danger" data-action="merge">Merge Selected -> Primary</button>' : ''}
          <button class="btn btn-default" data-action="close">Close</button>
        </div>
      </div>
    `;
    d.$body.html(body);

    d.$body.find('[data-action="close"]').on('click', () => d.hide());
    if (canCustomizeColumns) {
      d.$body.find('[data-action="columns"]').on('click', () => {
        _ld_open_columns_dialog(selectedColumnKeys, (nextKeys) => {
          selectedColumnKeys = nextKeys;
          renderTable();
        });
      });
    }

    d.$body.find('[data-action="merge"]').on('click', async () => {
      if (settings.merge_enabled === false) {
        frappe.msgprint('CRM Lead Dedupe merge is disabled for this site.');
        return;
      }

      const names = Array.from(_ld_checked_names(d.$body, []));

      if (!names.length) return frappe.msgprint('Select at least one row to merge.');
      await frappe.call('crm_lead_dedupe.api.crm_lead_merge.merge_crm_leads', {
        primary: primary_name,
        duplicates: names
      });
      d.hide();
      frappe.show_alert({ message: 'Merged successfully', indicator: 'green' });
      // refresh list or form if present
      if (frappe.listview_settings && window.cur_list && window.cur_list.doctype === 'CRM Lead') window.cur_list.refresh();
      if (window.cur_frm && window.cur_frm.doctype === 'CRM Lead' && window.cur_frm.doc && window.cur_frm.doc.name === primary_name) window.cur_frm.reload_doc();
    });

  } catch (e) {
    console.error('openCRMLeadDuplicatesDialog error:', e);
    frappe.msgprint('Could not load duplicates (see console).');
  }
}

// expose globally so list/form JS can call it
window.openCRMLeadDuplicatesDialog = openCRMLeadDuplicatesDialog;

