// apps/crm_lead_dedupe/crm_lead_dedupe/public/js/crm_lead_list.js
(function () {
  const doctype = 'CRM Lead';
  const existingSettings = frappe.listview_settings[doctype] || {};
  const existingOnload = existingSettings.onload;
  const existingRefresh = existingSettings.refresh;
  const dedupeFields = crmLeadDedupeEnabled('ui_enabled', 'hit_count_enabled')
    ? ['sr_dup_hit_count', 'sr_dup_unseen_hit', 'lead_name']
    : [];

  frappe.listview_settings[doctype] = {
    ...existingSettings,
    add_fields: Array.from(new Set([...(existingSettings.add_fields || []), ...dedupeFields])),

    onload(listview) {
      if (typeof existingOnload === 'function') {
        existingOnload(listview);
      }
      if (!crmLeadDedupeEnabled('ui_enabled')) {
        return;
      }
      installCRMLeadDedupeList(listview);
    },

    refresh(listview) {
      if (typeof existingRefresh === 'function') {
        existingRefresh(listview);
      }
      if (crmLeadDedupeEnabled('ui_enabled') && listview.crm_lead_dedupe_decorate) {
        listview.crm_lead_dedupe_decorate();
      }
    },

    // Don't try to inject HTML into "lead_name" formatter; it gets escaped by Frappe.
    formatters: {
      ...(existingSettings.formatters || {}),
    },
  };

  function installCRMLeadDedupeList(listview) {
    if (listview.crm_lead_dedupe_installed) {
      return;
    }
    listview.crm_lead_dedupe_installed = true;

    window.crm_lead_dedupe_open_duplicates = async function (name) {
      if (!name) return;
      if (!crmLeadDedupeEnabled('ui_enabled')) return;
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

    if (crmLeadDedupeEnabled('permission_filter_enabled')) {
      removeArchivedFilterFromRoute(listview);
    }

    // 1) Prefer duplicates first
    if (crmLeadDedupeEnabled('hit_count_enabled')) {
      listview.sort_by = 'sr_dup_hit_count';
      listview.sort_order = 'desc';
    }

    // 2) Minimal CSS for a compact pill
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
        @keyframes sr-dup-row-flash {
          0%, 100% { background: #fff; }
          50% { background: #fff3cd; }
        }
        .list-row.sr-dup-flash,
        .list-row.sr-dup-flash .list-row-col {
          animation: sr-dup-row-flash 1.4s ease-in-out infinite;
        }
        .list-row.sr-dup-flash {
          box-shadow: inset 3px 0 0 #f5a623;
        }
      `;
      document.head.appendChild(style);
    }

    // 3) Capture hit clicks before the list row navigation can consume them.
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

    // 4) Delegated click fallback for older event paths.
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
        scheduleHitDecorate();
      };
    }

    // 5) Decorate rows from fields already loaded with the list data.
    function decorateRows() {
      if (!crmLeadDedupeEnabled('ui_enabled', 'hit_count_enabled')) {
        listview.$result.find('.sr-hit-btn').remove();
        listview.$result.find('.sr-dup-flash').removeClass('sr-dup-flash');
        return;
      }

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

        const hits = cint(doc.sr_dup_hit_count || 0);
        const unseenHit = cint(doc.sr_dup_unseen_hit || 0);
        $row.toggleClass('sr-dup-flash', Boolean(unseenHit));
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

    function scheduleHitDecorate() {
      clearTimeout(listview.crm_lead_dedupe_hit_timer);
      listview.crm_lead_dedupe_hit_timer = setTimeout(decorateRows, 100);
    }

    listview.crm_lead_dedupe_decorate = scheduleHitDecorate;
    scheduleHitDecorate();

    // Optional belt-and-suspenders: re-decorate on list refresh events
    if (typeof listview.on === 'function') {
      listview.on('refresh', scheduleHitDecorate);
    }
  }
})();

function crmLeadDedupeEnabled(...features) {
  const settings = (frappe.boot && frappe.boot.crm_lead_dedupe) || {};
  return settings.enabled !== false && features.every(feature => settings[feature] !== false);
}

function removeArchivedFilterFromRoute(listview) {
  stripArchivedQueryParam();

  const hasArchivedFilter = (listview.filter_area.get() || [])
    .some(filter => filter[1] === 'sr_is_archived');
  if (!hasArchivedFilter) return;

  listview.filter_area.remove('sr_is_archived').then(() => {
    stripArchivedQueryParam();
  });
}

function stripArchivedQueryParam() {
  const url = new URL(window.location.href);
  if (!url.searchParams.has('sr_is_archived')) return;

  url.searchParams.delete('sr_is_archived');
  const nextUrl = `${url.pathname}${url.search}${url.hash}`;
  window.history.replaceState(window.history.state, '', nextUrl);
}

