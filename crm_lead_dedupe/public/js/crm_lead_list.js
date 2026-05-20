// apps/crm_lead_dedupe/crm_lead_dedupe/public/js/crm_lead_list.js
frappe.listview_settings['CRM Lead'] = {
  // Make sure these come back in the list row payload
  add_fields: ['sr_dup_hit_count', 'lead_name'],

  onload(listview) {
    window.crm_lead_dedupe_open_duplicates = async function (name) {
      if (!name) return;
      if (!window.openCRMLeadDuplicatesDialog) {
        await new Promise(resolve => frappe.require('/assets/crm_lead_dedupe/js/crm_lead_modal.js', resolve));
      }
      if (!window.openCRMLeadDuplicatesDialog) {
        frappe.msgprint('Could not load duplicate dialog. Please clear cache and try again.');
        return;
      }
      await window.openCRMLeadDuplicatesDialog({ primary_name: name });
    };

    async function openDuplicates(name) {
      await window.crm_lead_dedupe_open_duplicates(name);
    }

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
          flex:0 0 auto;
          padding:2px 8px; font-size:12px; line-height:1.1;
          border-radius:999px; border:1px solid #ffe69c;
          background:#fff3cd; color:#7a5b00; cursor:pointer;
          margin-left:8px; user-select:none;
          white-space:nowrap; vertical-align:middle;
          appearance:none;
        }
        .sr-hit-btn:hover{ background:#ffec99; }
      `;
      document.head.appendChild(style);
    }

    // 4) Capture hit clicks before the list row navigation can consume them.
    if (!window.crm_lead_dedupe_hit_capture_installed) {
      window.crm_lead_dedupe_hit_capture_installed = true;
      document.addEventListener('click', (event) => {
        const btn = event.target && event.target.closest && event.target.closest('.sr-hit-btn');
        if (!btn) return;

        event.preventDefault();
        event.stopPropagation();
        event.stopImmediatePropagation && event.stopImmediatePropagation();
        window.crm_lead_dedupe_open_duplicates(btn.getAttribute('data-name'));
      }, true);
    }

    // 5) Delegated click fallback for older event paths.
    listview.$result.off('click.crm_lead_dedupe', '.sr-hit-btn');
    listview.$result.on('click.crm_lead_dedupe', '.sr-hit-btn', async (e) => {
      e.preventDefault();
      e.stopPropagation();
      await openDuplicates(e.currentTarget.getAttribute('data-name'));
    });

    $(document).off('click.crm_lead_dedupe_hits', '.sr-hit-btn');
    $(document).on('click.crm_lead_dedupe_hits', '.sr-hit-btn', async (e) => {
      e.preventDefault();
      e.stopPropagation();
      await openDuplicates(e.currentTarget.getAttribute('data-name'));
    });

    const originalRender = listview.render && listview.render.bind(listview);
    if (originalRender && !listview.crm_lead_dedupe_render_wrapped) {
      listview.crm_lead_dedupe_render_wrapped = true;
      listview.render = function () {
        originalRender();
        scheduleHitRefresh();
      };
    }

    // 6) Refresh hit counts from server, then decorate visible rows.
    function refreshHitCounts() {
      const names = (listview.data || []).map(doc => doc.name).filter(Boolean);
      if (!names.length) return;

      frappe.call({
        method: 'crm_lead_dedupe.api.crm_lead_duplicates.get_hit_counts_for_crm_leads',
        args: { lead_names: names },
        callback(r) {
          const counts = (r.message && r.message.result) || {};
          decorateRows(counts);
        }
      });
    }

    function decorateRows(counts = {}) {
      const rows = listview.data || [];
      if (!rows.length) return;

      rows.forEach((doc) => {
        const escapedName = window.CSS && CSS.escape
          ? CSS.escape(doc.name)
          : String(doc.name).replace(/"/g, '\\"');

        const $named = listview.$result.find(`[data-name="${escapedName}"]`);
        const $row = $named.hasClass('list-row') ? $named : $named.closest('.list-row');
        if (!$row.length) return;

        const $subject = $row.find('.list-row-col.list-subject, .list-subject').first();
        if (!$subject.length) return;

        $subject.find('.sr-hit-btn').remove();

        const serverCount = counts[doc.name] && counts[doc.name].hit_count;
        const hits = cint(serverCount || doc.sr_dup_hit_count || 0);
        if (!hits) return;

        const text = hits === 1 ? '1 Hit' : `${hits} Hits`;
        const pill = `
          <button type="button" class="sr-hit-btn"
                data-name="${frappe.utils.escape_html(doc.name)}"
                title="View duplicates">${text}</button>
        `;

        // Place right after the bold name anchor if present, else append at end
        const $anchor = $subject.find('.level-item.bold, a.bold, a').first();
        const $pill = $(pill);
        $pill.on('mousedown', (e) => {
          e.preventDefault();
          e.stopPropagation();
        });
        $pill.on('click', async (e) => {
          await openDuplicates(e.currentTarget.getAttribute('data-name'));
        });

        if ($anchor.length) $anchor.after($pill);
        else $subject.append($pill);
      });
    }

    function scheduleHitRefresh() {
      clearTimeout(listview.crm_lead_dedupe_hit_timer);
      listview.crm_lead_dedupe_hit_timer = setTimeout(refreshHitCounts, 80);
    }

    listview.crm_lead_dedupe_decorate = scheduleHitRefresh;
    scheduleHitRefresh();

    // And on any DOM updates (paging, filters, quick edits, virtualized reflow).
    const target = listview.$result.get(0);
    if (target) {
      if (listview.crm_lead_dedupe_observer) {
        listview.crm_lead_dedupe_observer.disconnect();
      }
      const debounced = frappe.utils.debounce(scheduleHitRefresh, 80);
      listview.crm_lead_dedupe_observer = new MutationObserver(() => debounced());
      listview.crm_lead_dedupe_observer.observe(target, { childList: true, subtree: true });
    }

    // Optional belt-and-suspenders: re-decorate on list refresh events
    if (typeof listview.on === 'function') {
      listview.on('refresh', scheduleHitRefresh);
    }
  },

  refresh(listview) {
    if (listview.crm_lead_dedupe_decorate) {
      listview.crm_lead_dedupe_decorate();
    }
  },

  // Don't try to inject HTML into "lead_name" formatter; it gets escaped by Frappe.
  formatters: {}
};

