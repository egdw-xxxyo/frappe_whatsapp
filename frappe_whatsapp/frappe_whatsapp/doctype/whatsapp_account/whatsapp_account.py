# Copyright (c) 2025, Shridhar Patil and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.integrations.utils import make_post_request
from frappe.model.document import Document


class WhatsAppAccount(Document):
	def validate(self):
		self.validate_two_step_pin()

	def validate_two_step_pin(self):
		pin = self.two_step_pin
		if pin and not self.is_dummy_password(pin) and not (len(pin) == 6 and pin.isdigit()):
			frappe.throw(_("Two-Step Verification PIN must be exactly 6 digits"))

	def on_update(self):
		"""Check there is only one default of each type."""
		self.there_must_be_only_one_default()

	def there_must_be_only_one_default(self):
		"""If current WhatsApp Account is default, un-default all other accounts."""
		for field in ("is_default_incoming", "is_default_outgoing"):
			if not self.get(field):
				continue

			for whatsapp_account in frappe.get_all("WhatsApp Account", filters={field: 1}):
				if whatsapp_account.name == self.name:
					continue

				whatsapp_account = frappe.get_doc("WhatsApp Account", whatsapp_account.name)
				whatsapp_account.set(field, 0)
				whatsapp_account.save()

	@frappe.whitelist()
	def subscribe_app(self):
		"""Subscribe this app to webhooks for the WhatsApp Business Account.

		Required after phone number registration to receive incoming messages.
		Calls POST /{version}/{business_id}/subscribed_apps on the Graph API.
		"""
		for field in ("url", "version", "business_id"):
			if not self.get(field):
				frappe.throw(_("{0} is required to subscribe the app").format(
					frappe.bold(self.meta.get_label(field))
				))

		token = self.get_password("token")
		if not token:
			frappe.throw(_("Access token is required to subscribe the app"))

		endpoint = f"{self.url}/{self.version}/{self.business_id}/subscribed_apps"
		headers = {
			"authorization": f"Bearer {token}",
			"content-type": "application/json",
		}

		try:
			response = make_post_request(endpoint, headers=headers)
		except Exception as e:
			error_message = str(e)
			if frappe.flags.integration_request:
				err = frappe.flags.integration_request.json().get("error", {})
				if err:
					error_message = err.get("message") or err.get("Error") or error_message
			frappe.throw(_("Failed to subscribe app to webhooks: {0}").format(error_message))

		if not response.get("success"):
			frappe.throw(_("Subscription was not successful: {0}").format(frappe.as_json(response)))

		frappe.logger().info(
			f"WhatsApp app subscribed to webhooks for business_id={self.business_id}"
		)
		return response

	@frappe.whitelist()
	def register_phone(self):
		"""Register the phone number with the Cloud API using the stored PIN, then subscribe the app.

		Calls POST /{version}/{phone_id}/register on the Graph API.
		"""
		frappe.only_for("System Manager")

		for field in ("url", "version", "phone_id"):
			if not self.get(field):
				frappe.throw(_("{0} is required to register the phone number").format(
					frappe.bold(self.meta.get_label(field))
				))

		token = self.get_password("token")
		if not token:
			frappe.throw(_("Access token is required to register the phone number"))

		pin = self.get_password("two_step_pin", raise_exception=False)
		if not pin:
			frappe.throw(_("Set the Two-Step Verification PIN before registering the phone number"))

		endpoint = f"{self.url}/{self.version}/{self.phone_id}/register"
		headers = {
			"authorization": f"Bearer {token}",
			"content-type": "application/json",
		}

		try:
			response = make_post_request(
				endpoint,
				headers=headers,
				json={"messaging_product": "whatsapp", "pin": pin},
			)
		except Exception as e:
			error_message = str(e)
			if frappe.flags.integration_request:
				err = frappe.flags.integration_request.json().get("error", {})
				if err:
					error_message = err.get("error_user_msg") or err.get("message") or error_message
			frappe.throw(_("Failed to register phone number: {0}").format(error_message))

		if not response.get("success"):
			frappe.throw(_("Registration was not successful: {0}").format(frappe.as_json(response)))

		frappe.logger().info(f"WhatsApp phone number registered: phone_id={self.phone_id}")

		if self.business_id:
			self.subscribe_app()

		return response

	@frappe.whitelist()
	def reveal_two_step_pin(self):
		frappe.only_for("System Manager")
		return self.get_password("two_step_pin", raise_exception=False)
