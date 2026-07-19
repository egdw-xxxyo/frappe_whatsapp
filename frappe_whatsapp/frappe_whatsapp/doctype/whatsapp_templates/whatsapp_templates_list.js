frappe.listview_settings['WhatsApp Templates'] = {

	onload: function(listview) {
		// Hide Meta's built-in sample/system templates by default (hello_world,
		// jaspers_market_* demos, 3p integration test template) — remove the
		// filter manually to see them.
		if (!listview.filter_area.get().some((f) => f[1] === "actual_name")) {
			listview.filter_area.add([
				["WhatsApp Templates", "actual_name", "not in", ["hello_world", "3p_direct_integration_test_template"]],
				["WhatsApp Templates", "actual_name", "not like", "jaspers_market%"],
			]);
		}
		listview.page.add_inner_button(__("Sync from Meta"), function() {
			frappe.call({
				method: 'frappe_whatsapp.frappe_whatsapp.doctype.whatsapp_templates.whatsapp_templates.fetch',
				freeze: true,
				freeze_message: __("Syncing templates from Meta..."),
				callback: function(r) {
					if (r.message) {
						frappe.msgprint({
							title: __("Sync Complete"),
							message: r.message,
							indicator: "green"
						});
						listview.refresh();
					}
				}
			});
		});
	}
};