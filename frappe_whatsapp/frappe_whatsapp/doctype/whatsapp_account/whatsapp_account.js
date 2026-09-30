// Copyright (c) 2025, Shridhar Patil and contributors
// For license information, please see license.txt

frappe.ui.form.on("WhatsApp Account", {
	refresh(frm) {
		if (!frm.is_new()) {
			frm.add_custom_button(__("Subscribe App to Webhooks"), () => {
				frappe.confirm(
					__("Subscribe this app to webhooks for WhatsApp Business Account {0}?", [
						frm.doc.business_id || frm.doc.account_name,
					]),
					() => {
						frm.call({
							doc: frm.doc,
							method: "subscribe_app",
							freeze: true,
							freeze_message: __("Subscribing app to webhooks..."),
							callback: (r) => {
								if (!r.exc) {
									frappe.show_alert({
										message: __("App subscribed to webhooks"),
										indicator: "green",
									});
								}
							},
						});
					}
				);
			});

			frm.add_custom_button(__("Register Phone Number"), () => {
				if (frm.is_dirty()) {
					frappe.msgprint(__("Save the document before registering the phone number"));
					return;
				}
				frappe.confirm(
					__("Register phone number {0} with the WhatsApp Cloud API using the stored PIN?", [
						frm.doc.phone_id,
					]),
					() => {
						frm.call({
							doc: frm.doc,
							method: "register_phone",
							freeze: true,
							freeze_message: __("Registering phone number..."),
							callback: (r) => {
								if (!r.exc) {
									frappe.show_alert({
										message: __("Phone number registered"),
										indicator: "green",
									});
								}
							},
						});
					}
				);
			});

			frm.add_custom_button(__("Fetch Number Info"), () => {
				frm.call({
					doc: frm.doc,
					method: "fetch_number_info",
					freeze: true,
					callback: (r) => {
						if (!r.exc) frm.reload_doc();
					},
				});
			});

			if (frm.doc.two_step_pin) {
				frm.add_custom_button(__("Show PIN"), () => {
					frm.call({
						doc: frm.doc,
						method: "reveal_two_step_pin",
						callback: (r) => {
							if (!r.exc) {
								frappe.msgprint({
									title: __("Two-Step Verification PIN"),
									message: `<b style="font-size: 1.5em; letter-spacing: 0.2em">${frappe.utils.escape_html(
										r.message || ""
									)}</b>`,
								});
							}
						},
					});
				});
			}
		}
	},
});
