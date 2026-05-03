from __future__ import annotations

import base64
import unittest

from nemotronos_tools.tools.gmail import (
    GMAIL_DRAFTS_URL,
    build_gmail_draft_message,
    create_gmail_draft,
)


class _FakeDraftCreateRequest:
    def __init__(self, body: dict) -> None:
        self.body = body

    def execute(self) -> dict:
        return {"id": "draft-123", "message": {"id": "message-456"}}


class _FakeDrafts:
    def __init__(self) -> None:
        self.created_body: dict | None = None

    def create(self, userId: str, body: dict) -> _FakeDraftCreateRequest:  # noqa: N803
        self.created_body = {"userId": userId, "body": body}
        return _FakeDraftCreateRequest(body)


class _FakeUsers:
    def __init__(self, drafts: _FakeDrafts) -> None:
        self._drafts = drafts

    def drafts(self) -> _FakeDrafts:
        return self._drafts


class _FakeGmailService:
    def __init__(self) -> None:
        self.drafts_resource = _FakeDrafts()

    def users(self) -> _FakeUsers:
        return _FakeUsers(self.drafts_resource)


class GmailToolTests(unittest.TestCase):
    def test_builds_plain_text_gmail_draft_message(self) -> None:
        message = build_gmail_draft_message(
            {
                "to": "alex@example.com",
                "cc": ["team@example.com"],
                "subject": "Hackathon update",
                "body": "I finished the draft slice.",
            }
        )

        self.assertEqual(message["To"], "alex@example.com")
        self.assertEqual(message["Cc"], "team@example.com")
        self.assertEqual(message["Subject"], "Hackathon update")
        self.assertIn("I finished the draft slice.", message.get_content())

    def test_rejects_domain_without_email_address(self) -> None:
        with self.assertRaisesRegex(ValueError, "must be email addresses"):
            build_gmail_draft_message(
                {
                    "to": "example.com",
                    "subject": "Nemotron OS",
                    "body": "This is a draft.",
                }
            )

    def test_create_gmail_draft_omits_body_from_result(self) -> None:
        service = _FakeGmailService()
        arguments = {
            "to": "alex@example.com",
            "subject": "Private subject",
            "body": "Private draft body.",
        }
        message = build_gmail_draft_message(arguments)

        result = create_gmail_draft(service, message, arguments)

        self.assertEqual(result["draft_id"], "draft-123")
        self.assertEqual(result["message_id"], "message-456")
        self.assertEqual(result["draft_url"], GMAIL_DRAFTS_URL)
        self.assertEqual(result["body_characters"], len("Private draft body."))
        self.assertNotIn("body", result)
        created_body = service.drafts_resource.created_body
        assert created_body is not None
        raw = created_body["body"]["message"]["raw"]
        decoded = base64.urlsafe_b64decode(raw.encode("ascii")).decode("utf-8")
        self.assertIn("Private draft body.", decoded)


if __name__ == "__main__":
    unittest.main()
