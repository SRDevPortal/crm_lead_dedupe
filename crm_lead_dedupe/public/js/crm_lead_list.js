// apps/crm_lead_dedupe/crm_lead_dedupe/public/js/crm_lead_list.js
frappe.listview_settings['CRM Lead'] = {
  // Make sure these come back in the list row payload
  add_fields: ['sr_dup_hit_count', 'lead_name'],

  onload(listview) {
    // 1) Hide archived by default (add only once)
    const hasArchived = (listview.filter_area.get() || []).some(f => f[1] === 'sr_is_archived');
    if (!hasArchived) {
      listview.filter_area.add([['CRM Lead', 'sr_is_archived', '=', 0]]);
      listview.run(); // apply immediately
    }

    // 2) Prefer duplicates first
    listview.sort_by = 'sr_dup_hit_count';
    listview.sort_order = 'desc';

    // 3) Minimal CSS for a compact pill
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

    // 4) Delegated click: open your modal (works across re-renders)
    listview.$result.on('click', '.sr-hit-btn', async (e) => {
      e.preventDefault();
      e.stopPropagation();
      const name = e.currentTarget.getAttribute('data-name');
      if (name) {
        if (!window.openCRMLeadDuplicatesDialog) {
          await new Promise(resolve => frappe.require('/assets/crm_lead_dedupe/js/crm_lead_modal.js', resolve));
        }
        await window.openCRMLeadDuplicatesDialog({ primary_name: name });
      }
    });

    // 5) Decorate rows AFTER the list actually paints (robust on v15 virtualized list)
    function decorateRows() {
      const rows = listview.data || [];
      if (!rows.length) return;

      rows.forEach((doc) => {
        const hits = cint(doc.sr_dup_hit_count || 0);
        if (!hits) return;

        // Find the rendered row by data-name, then its subject cell (bold name)
        const $row = listview.$result.find(`[data-name="${CSS.escape(doc.name)}"]`).closest('.list-row');
        if (!$row.length) return;

        const $subject = $row.find('.list-row-col.list-subject');
        if (!$subject.length) return;

        // Avoid duplicates on subsequent re-renders
        if ($subject.find(`.sr-hit-btn[data-name="${CSS.escape(doc.name)}"]`).length) return;

        const text = hits === 1 ? '1 Hit' : `${hits} Hits`;
        const pill = `
          <span class="sr-hit-btn"
                data-name="${frappe.utils.escape_html(doc.name)}"
                title="View duplicates">${text}</span>
        `;

        // Place right after the bold name anchor if present, else append at end
        const $anchor = $subject.find('.level-item.bold');
        if ($anchor.length) $anchor.after(pill);
        else $subject.append(pill);
      });
    }

    // Run once after the first paint.
    setTimeout(decorateRows, 0);

    // And on any DOM updates (paging, filters, quick edits, virtualized reflow).
    const target = listview.$result.get(0);
    if (target) {
      const debounced = frappe.utils.debounce(decorateRows, 60);
      new MutationObserver(() => debounced()).observe(target, { childList: true, subtree: true });
    }

    // Optional belt-and-suspenders: re-decorate on list refresh events
    if (typeof listview.on === 'function') {
      listview.on('refresh', () => setTimeout(decorateRows, 0));
    }
  },

  // Don't try to inject HTML into "lead_name" formatter; it gets escaped by Frappe.
  formatters: {}
};

