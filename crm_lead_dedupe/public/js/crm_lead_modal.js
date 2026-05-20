// apps/crm_lead_dedupe/crm_lead_dedupe/public/js/crm_lead_modal.js

// ---------- helpers ----------
function _ld_esc(t) {
  return frappe.utils.escape_html(t || "-").replace(/\n/g, "<br>");
}
function _ld_clean(t) {
  return (t || "").replace(/<[^>]*>/g, "").replace(/&nbsp;/g, " ").trim();
}
function _ld_css_block() {
  return `
  <style>
    .ld-wrap { padding: 16px; }
    .ld-head { margin: 0 0 10px; padding: 0 0 8px; border-bottom: 1px solid #eee; }
    .ld-muted { color: #666; }
    .ld-table { width: 100%; border-collapse: collapse; }
    .ld-table th, .ld-table td { padding: 8px 10px; border-bottom: 1px solid #f0f0f0; vertical-align: top; }
    .ld-table th { font-weight: 600; white-space: nowrap; }
    .ld-badge { display: inline-block; padding: 2px 8px; border-radius: 999px; background: #eef3ff; border: 1px solid #dbe3ff; }
    .ld-actions { position: sticky; bottom: 0; z-index: 1; background: #fff; padding: 10px 16px; border-top: 1px solid #eee; display: flex; gap: 8px; justify-content: flex-end; }
    .ld-row-subtle { color: #444; font-size: 12px; }
    @media (max-width: 992px) {
      .ld-hide-md { display: none; }
    }
    @media print {
      .ld-actions { display:none !important; }
    }
  </style>`;
}

function _ld_table_rows(rows) {
  const doctypeSlug = (frappe.router && frappe.router.slug)
    ? frappe.router.slug('CRM Lead')
    : 'crm-lead';

  return rows.map((r, idx) => `
    <tr data-name="${_ld_esc(r.name)}">
      <td><input type="checkbox" class="ld-check" ${idx===0?'checked':''}/></td>
      <td><a class="bold" href="/app/${doctypeSlug}/${_ld_esc(r.name)}" target="_blank">${_ld_esc(r.name)}</a></td>
      <td class="ld-hide-md">${_ld_esc(r.owner)}</td>
      <td><span class="ld-badge">${_ld_esc(r.stage)}</span></td>
      <td class="ld-hide-md">${_ld_esc(r.creation ? frappe.datetime.str_to_user(r.creation) : '-')}</td>
      <td>${_ld_esc(r.mobile_no)}</td>
      <td>${_ld_esc(r.lead_name)}</td>
      <td class="ld-hide-md">${_ld_esc(r.platform)}</td>
      <td>${_ld_esc(r.source)}</td>
      <td style="text-align:right; width:70px">${_ld_esc(String(r.score))}</td>
    </tr>
  `).join("");
}

function _ld_build_table(rows) {
  return `
    <table class="ld-table">
      <thead>
        <tr>
          <th style="width:34px"></th>
          <th>Lead Id</th>
          <th class="ld-hide-md">Owner</th>
          <th>Stage</th>
          <th class="ld-hide-md">Creation</th>
          <th>Mobile</th>
          <th>Full Name</th>
          <th class="ld-hide-md">Platform</th>
          <th>Source</th>
          <th style="text-align:right">Score</th>
        </tr>
      </thead>
      <tbody>${_ld_table_rows(rows)}</tbody>
    </table>
  `;
}

// ---------- main modal ----------
async function openCRMLeadDuplicatesDialog({ primary_name }) {
  try {
    if (!primary_name) return;

    const d = new frappe.ui.Dialog({
      title: 'Merged records',
      size: 'large',
      static: true
    });

    const $dlg = d.$wrapper.find(".modal-dialog");
    $dlg.addClass("modal-xl");
    d.$wrapper.find(".modal-body").css({ maxHeight: "80vh", overflow: "auto", paddingBottom: 0 });

    d.$body.html("<div style='padding:16px' class='text-muted'>Loading duplicates...</div>");
    d.show();

    const { message: rows = [] } = await frappe.call(
      'crm_lead_dedupe.api.crm_lead_duplicates.get_duplicates_for_crm_lead',
      { lead_name: primary_name }
    );

    const body = `
      ${_ld_css_block()}
      <div class="ld-wrap">
        <div class="ld-head">
          <div><b>Primary Lead:</b> ${_ld_esc(primary_name)}</div>
          <div class="ld-muted">${rows.length ? rows.length : 'No'} duplicate${rows.length===1?'':'s'} found by mobile.</div>
        </div>
        ${rows.length ? _ld_build_table(rows) : "<p class='ld-muted'>No duplicates found.</p>"}
        <div class="ld-actions">
          <button class="btn btn-danger" data-action="merge">Merge Selected -> Primary</button>
          <button class="btn btn-default" data-action="close">Close</button>
        </div>
      </div>
    `;
    d.$body.html(body);

    d.$body.find('[data-action="close"]').on('click', () => d.hide());

    d.$body.find('[data-action="merge"]').on('click', async () => {
      const names = Array.from(d.$body.find('tbody .ld-check:checked').map((_, el) =>
        el.closest('tr').getAttribute('data-name')
      )).filter(Boolean);

      if (!names.length) return frappe.msgprint('Select at least one row to merge.');
      await frappe.call('crm_lead_dedupe.api.crm_lead_merge.merge_crm_leads', {
        primary: primary_name,
        duplicates: names
      });
      d.hide();
      frappe.show_alert({ message: 'Merged successfully', indicator: 'green' });
      // refresh list or form if present
      if (frappe.listview_settings && cur_list && cur_list.doctype === 'CRM Lead') cur_list.refresh();
      if (cur_frm && cur_frm.doctype === 'CRM Lead' && cur_frm.doc && cur_frm.doc.name === primary_name) cur_frm.reload_doc();
    });

  } catch (e) {
    console.error('openCRMLeadDuplicatesDialog error:', e);
    frappe.msgprint('Could not load duplicates (see console).');
  }
}

// expose globally so list/form JS can call it
window.openCRMLeadDuplicatesDialog = openCRMLeadDuplicatesDialog;

