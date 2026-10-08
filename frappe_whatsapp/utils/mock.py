"""Simulated Meta Cloud API for dev/test sites.

An account with `mock_mode` set never talks to Meta: what would be a Graph call is answered
here with the response Meta would give, and the delivery receipts Meta would push back are
fed through the real webhook handler. Never active when the site's `instance_env` is "prod".
"""

import frappe

MEDIA_PREFIX = "mock:"


def is_mock(account):
	if frappe.conf.get("instance_env") == "prod" or not account:
		return False
	if isinstance(account, str):
		return bool(frappe.db.get_value("WhatsApp Account", account, "mock_mode"))
	return bool(account.get("mock_mode"))


def graph_post(account, data):
	"""Answer a POST to {phone_id}/messages."""
	if data.get("status") == "read":
		return {"success": True}
	message_id = f"wamid.MOCK{frappe.generate_hash(length=24)}"
	frappe.enqueue(
		"frappe_whatsapp.utils.mock.deliver",
		account=account.name,
		phone_id=account.phone_id,
		message_id=message_id,
		to=data.get("to"),
		enqueue_after_commit=True,
	)
	return {
		"messaging_product": "whatsapp",
		"contacts": [{"input": data.get("to"), "wa_id": data.get("to")}],
		"messages": [{"id": message_id}],
	}


def upload_media():
	return f"{MEDIA_PREFIX}out-{frappe.generate_hash(length=16)}"


def get_media(media_id):
	"""Stand-in for Meta's two media GETs (`/{id}` then the url inside): `media_id` is
	`mock:<File name>` and doubles as the download url. Mimics a `requests` response."""
	import mimetypes
	from types import SimpleNamespace

	file_doc = frappe.get_doc("File", media_id[len(MEDIA_PREFIX) :])
	mime = mimetypes.guess_type(file_doc.file_name or "")[0] or "application/octet-stream"
	return SimpleNamespace(
		status_code=200,
		json=lambda: {"url": media_id, "mime_type": mime},
		content=file_doc.get_content(),
	)


def post_webhook(account, value):
	"""Feed a Meta-shaped `value` through the real webhook handler, as if Meta had called it."""
	from frappe_whatsapp.utils.webhook import post

	value.setdefault("messaging_product", "whatsapp")
	value["metadata"] = {"display_phone_number": account.display_phone_number, "phone_number_id": account.phone_id}
	payload = {
		"object": "whatsapp_business_account",
		"entry": [{"id": account.business_id or "MOCK", "changes": [{"field": "messages", "value": value}]}],
	}
	original = frappe.local.form_dict
	frappe.local.form_dict = frappe._dict(payload)
	try:
		return post()
	finally:
		frappe.local.form_dict = original


def deliver(account, phone_id, message_id, to):
	"""sent -> delivered receipts for a mock outgoing message."""
	import time

	acc = frappe.get_doc("WhatsApp Account", account)
	for status in ("sent", "delivered"):
		post_webhook(
			acc,
			{"statuses": [{"id": message_id, "status": status, "recipient_id": to, "timestamp": str(int(time.time()))}]},
		)
		frappe.db.commit()
