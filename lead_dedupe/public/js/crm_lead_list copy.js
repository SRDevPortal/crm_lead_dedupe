// apps/lead_dedupe/lead_dedupe/public/js/crm_lead_list.js
frappe.listview_settings['CRM Lead'] = {
  // make sure we get these fields in the row JSON
  add_fields: ['sr_dup_hit_count', 'lead_name'],

  onload(listview) {
    // Hide archived by default (add only if not already present)
    const hasArchived = (listview.filter_area.get() || [])
      .some(f => f[1] === 'sr_is_archived');
    if (!hasArchived) {
      listview.filter_area.add([['CRM Lead', 'sr_is_archived', '=', 0]]);
      listview.run(); // apply immediately
    }

    // Prefer duplicates first
    listview.sort_by = 'sr_dup_hit_count';
    listview.sort_order = 'desc';

    // --- Minimal CSS for a compact "pill button" ---
    if (!document.getElementById('sr-hit-btn-style')) {
      const style = document.createElement('style');
      style.id = 'sr-hit-btn-style';
      style.textContent = `
        .sr-hit-btn{
          display:inline-flex; align-items:center; gap:6px;
          padding:2px 8px; font-size:12px; line-height:1.1;
          border-radius:999px; border:1px solid #ffe69c;
          background:#fff3cd; color:#7a5b00; cursor:pointer;
          margin-left:8px; user-select:none;
        }
        .sr-hit-btn:hover{ background:#ffec99; }
      `;
      document.head.appendChild(style);
    }

    // Click → open your modal
    listview.$result.on('click', '.sr-hit-btn', async (e) => {
      e.stopPropagation();
      const leadName = e.currentTarget.getAttribute('data-name');
      if (leadName) await window.openCRMLeadDuplicatesDialog({ primary_name: leadName });
    });

    // Append the button into the Full Name cell after each render
    function decorateRows() {
      (listview.data || []).forEach((doc) => {
        const hits = cint(doc.sr_dup_hit_count || 0);
        if (!hits) return;

        // ✅ Find any child with data-name, then go up to the row
        const $row = listview.$result
          .find(`[data-name="${CSS.escape(doc.name)}"]`)
          .closest('.list-row');
        if (!$row.length) return;

        // ✅ Full Name lives in the special subject column
        const $subjectCell = $row.find('.list-row-col.list-subject');
        if (!$subjectCell.length) return;

        // avoid duplicates on re-render
        if ($subjectCell.find(`.sr-hit-btn[data-name="${CSS.escape(doc.name)}"]`).length) return;

        const text = hits === 1 ? '1 Hit' : `${hits} Hits`;
        const btn = $(
          `<span class="sr-hit-btn" title="View duplicates"
                  data-name="${frappe.utils.escape_html(doc.name)}">${text}</span>`
        );

        // place right after the bold name anchor if present
        const $anchor = $subjectCell.find('.level-item.bold');
        if ($anchor.length) $anchor.after(btn);
        else $subjectCell.append(btn);
      });
    }

    // Run once and on any DOM updates (paging, filters, refresh)
    setTimeout(decorateRows, 0);
    const target = listview.$result.get(0);
    if (target) {
      const debounced = frappe.utils.debounce(decorateRows, 60);
      new MutationObserver(debounced).observe(target, { childList: true, subtree: true });
    }
  },

  // Remove the old ID-column pill if you had it before.
  // If you still want it on the ID too, keep the formatter below;
  // otherwise, leave `formatters` empty.
  formatters: { }
};
