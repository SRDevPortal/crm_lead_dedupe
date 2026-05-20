// apps/crm_lead_dedupe/crm_lead_dedupe/public/js/crm_lead_form.js
frappe.ui.form.on('CRM Lead', {
  async before_save(frm) {
    // Proactively clear a stale "Duplicate Of" so server link validation can't fail
    if (frm.doc.sr_duplicate_of) {
      try {
        await frappe.call('crm_lead_dedupe.api.dup_fix.fix_duplicate_of_if_stale', {
          name: frm.doc.name || ''
        });
      } catch (e) {
        // non-fatal; save will proceed
        console.warn('fix_duplicate_of_if_stale failed', e);
      }
    }
  },

  after_save(frm) {
    if (cur_list && cur_list.doctype === 'CRM Lead') {
      cur_list.refresh();
    }
  },

  refresh(frm) {
    const archived = cint(frm.doc.sr_is_archived);

    if (archived) {
      // 1) Hard lock the form UI
      frm.disable_save();
      frm.set_read_only();
      frm.page.clear_actions_menu();
      frm.page.set_primary_action(null);
      frm.page.set_secondary_action(null);
      frm.clear_custom_buttons && frm.clear_custom_buttons();

      // 2) Make all fields + child tables visually read-only
      (frm.meta.fields || []).forEach(df => {
        if (df.fieldtype === 'Table' && frm.fields_dict[df.fieldname]?.grid) {
          const grid = frm.fields_dict[df.fieldname].grid;
          grid.wrapper.find('.grid-add-row, .grid-add-multiple-rows, .grid-insert-row, .grid-delete-row, .grid-remove-rows, .grid-row-check, .grid-editable-col, .grid-append-row').hide();
          grid.wrapper.find('.btn-open-row, .grid-row').each((_, el) => {
            el.onclick = (e) => { e.stopPropagation(); return false; };
          });
          grid.wrapper.find('.grid-body').addClass('disabled');
        }
        const c = frm.fields_dict[df.fieldname];
        if (c?.df && !c.df.read_only) {
          frm.set_df_property(df.fieldname, 'read_only', 1);
        }
      });

      // 3) Optional: hide comment/email composer
      $('.comment-input-container').hide();
      $('[data-label="New%20Email"]').closest('button, .btn').hide();

      // 4) Banner
      frm.dashboard.set_headline_alert(
        '<span class="fa fa-lock" style="margin-right:6px"></span> Archived - view only (no edits allowed).',
        'yellow'
      );

      return; // don't show merge button on archived
    }

    // Active records: show duplicates button if there are hits
    if (!frm.is_new() && cint(frm.doc.sr_dup_hit_count) > 0) {
      frm.add_custom_button('View & Merge Duplicates', async () => {
        if (!window.openCRMLeadDuplicatesDialog) {
          await new Promise(resolve => frappe.require('/assets/crm_lead_dedupe/js/crm_lead_modal.js', resolve));
        }
        window.openCRMLeadDuplicatesDialog({ primary_name: frm.doc.name });
      }).addClass('btn-danger text-dark');
    }
  }
});

