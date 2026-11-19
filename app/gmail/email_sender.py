"""Gmail Email Sender Service.

Constructs RFC 2822 compliant MIME messages and delivers replies via Gmail API.
Ensures proper thread preservation and anti-duplicate guards.
"""

import base64
import logging
from email.mime.text import MIMEText
from typing import Optional

logger = logging.getLogger(__name__)


class EmailSender:
    """Delivers formatted email replies through Gmail API."""

    def __init__(self, gmail_service):
        self.service = gmail_service

    def send_reply(
        self,
        to_email: str,
        subject: str,
        reply_body: str,
        thread_id: str,
        in_reply_to_header: Optional[str] = None
    ) -> Optional[str]:
        """Send a reply to an email thread via Gmail API.
        
        Returns the sent Gmail message ID upon success, or None on failure.
        """
        try:
            # Ensure subject has Re: prefix
            clean_subject = subject if subject.lower().startswith("re:") else f"Re: {subject}"

            mime_msg = MIMEText(reply_body, "plain", "utf-8")
            mime_msg["to"] = to_email
            mime_msg["subject"] = clean_subject

            if in_reply_to_header:
                mime_msg["In-Reply-To"] = in_reply_to_header
                mime_msg["References"] = in_reply_to_header

            raw_bytes = mime_msg.as_bytes()
            raw_b64 = base64.urlsafe_b64encode(raw_bytes).decode("utf-8")

            body = {
                "raw": raw_b64,
                "threadId": thread_id
            }

            result = self.service.users().messages().send(
                userId="me",
                body=body
            ).execute()

            sent_id = result.get("id")
            logger.info("Successfully sent email reply to %s (Message ID: %s, Thread: %s)", to_email, sent_id, thread_id)
            return sent_id
        except Exception as e:
            logger.error("Failed to deliver email reply to %s: %s", to_email, e)
            raise

    def send_new_email(
        self,
        to_email: str,
        subject: str,
        body: str,
        cc_emails: Optional[str] = None
    ) -> Optional[str]:
        """Send a new standalone email with optional CC recipients via Gmail API."""
        try:
            mime_msg = MIMEText(body, "plain", "utf-8")
            mime_msg["to"] = to_email
            mime_msg["subject"] = subject

            if cc_emails:
                mime_msg["cc"] = cc_emails

            raw_bytes = mime_msg.as_bytes()
            raw_b64 = base64.urlsafe_b64encode(raw_bytes).decode("utf-8")

            result = self.service.users().messages().send(
                userId="me",
                body={"raw": raw_b64}
            ).execute()

            sent_id = result.get("id")
            logger.info("Successfully dispatched new email to %s (CC: %s, Message ID: %s)", to_email, cc_emails, sent_id)
            return sent_id
        except Exception as e:
            logger.error("Failed to dispatch new email to %s: %s", to_email, e)
            raise
