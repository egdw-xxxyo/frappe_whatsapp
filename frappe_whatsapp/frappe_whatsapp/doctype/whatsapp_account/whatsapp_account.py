# Copyright (c) 2025, Shridhar Patil and contributors
# For license information, please see license.txt

import hashlib

import frappe
import requests
from frappe import _
from frappe.integrations.utils import make_get_request, make_post_request
from frappe.model.document import Document
from frappe.utils import now_datetime

PROFILE_FIELDS = (
	"display_phone_number",
	"verified_name",
	"quality_rating",
	"messaging_limit",
	"about",
	"address",
	"description",
	"email",
	"vertical",
	"websites",
	"profile_image",
	"profile_synced_on",
)


class WhatsAppAccount(Document):
	def validate(self):
		self.validate_two_step_pin()
		if self.phone_id and (self.has_value_changed("phone_id") or not self.display_phone_number):
			self.load_number_info(silent=True)

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

		self.load_number_info(silent=True)
		self.db_set({field: self.get(field) for field in PROFILE_FIELDS})
		return response

	@frappe.whitelist()
	def reveal_two_step_pin(self):
		frappe.only_for("System Manager")
		return self.get_password("two_step_pin", raise_exception=False)

	def load_number_info(self, silent=False):
		"""Read the number and its business profile from the Graph API: display number,
		verified name, quality and limit, plus the profile shown to customers (photo,
		about, description, address, email, websites, category)."""
		token = self.get_password("token", raise_exception=False)
		if not (self.url and self.version and self.phone_id and token):
			return
		base = f"{self.url}/{self.version}/{self.phone_id}"
		headers = {"authorization": f"Bearer {token}"}
		try:
			info = make_get_request(
				base,
				headers=headers,
				params={"fields": "display_phone_number,verified_name,quality_rating,messaging_limit_tier"},
			)
		except Exception as e:
			if silent:
				frappe.log_error(title="WhatsApp number info fetch failed", message=str(e))
				return
			frappe.throw(_("Failed to fetch phone number info: {0}").format(str(e)))
		self.display_phone_number = info.get("display_phone_number")
		self.verified_name = info.get("verified_name")
		self.quality_rating = info.get("quality_rating")
		self.messaging_limit = info.get("messaging_limit_tier")

		try:
			profile = make_get_request(
				f"{base}/whatsapp_business_profile",
				headers=headers,
				params={"fields": "about,address,description,email,profile_picture_url,websites,vertical"},
			)
			profile = (profile.get("data") or [{}])[0]
		except Exception as e:
			frappe.log_error(title="WhatsApp business profile fetch failed", message=str(e))
			profile = None
		if profile is not None:
			for field in ("about", "address", "description", "email", "vertical"):
				self.set(field, profile.get(field))
			self.websites = "\n".join(profile.get("websites") or [])
			self.store_profile_picture(profile.get("profile_picture_url"))
		self.profile_synced_on = now_datetime()

	def store_profile_picture(self, url):
		"""Keep a copy of the profile photo: Meta's URL is signed and expires."""
		if not url:
			self.profile_image = None
			return
		if self.is_new():
			return
		try:
			response = requests.get(url, timeout=20)
			response.raise_for_status()
		except Exception as e:
			frappe.log_error(title="WhatsApp profile photo download failed", message=str(e))
			return
		content = response.content
		if self.profile_image:
			current = frappe.db.get_value("File", {"file_url": self.profile_image}, "content_hash")
			if current and current == hashlib.md5(content).hexdigest():
				return
		file = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": f"whatsapp-{self.phone_id}.jpg",
				"attached_to_doctype": self.doctype,
				"attached_to_name": self.name,
				"attached_to_field": "profile_image",
				"is_private": 0,
				"content": content,
			}
		).insert(ignore_permissions=True)
		self.profile_image = file.file_url

	def save_number_info(self):
		self.load_number_info()
		self.db_set({field: self.get(field) for field in PROFILE_FIELDS})

	@frappe.whitelist()
	def fetch_number_info(self):
		self.check_permission("write")
		self.save_number_info()
		return {field: self.get(field) for field in PROFILE_FIELDS}
