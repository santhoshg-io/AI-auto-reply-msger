"""Gmail Email Fetcher & Content Extractor.

Retrieves real unread emails from the user's Gmail inbox and extracts clean plain text.
"""

import base64
import logging
import re
from typing import List, Dict, Any, Optional
from email.utils import parseaddr

logger = logging.getLogger(__name__)


class EmailFetcher:
    """Fetches and normalizes incoming messages from Gmail API."""

    def __init__(self, gmail_service):
        self.service = gmail_service

    def fetch_unread_emails(self, max_results: int = 10, already_processed_check=None) -> List[Dict[str, Any]]:
        """Fetch up to max_results unread messages from the primary inbox.
        
        If already_processed_check callable is provided, skips fetching details
        for messages that are already recorded in the database.
        """
        try:
            results = self.service.users().messages().list(
                userId="me",
                q="is:unread in:inbox",
                maxResults=max_results
            ).execute()

            messages = results.get("messages", [])
            logger.info("Found %d unread emails in inbox.", len(messages))

            parsed_emails = []
            for msg_meta in messages:
                msg_id = msg_meta["id"]

                # Optimization: Skip fetching full payload if already processed in database
                if already_processed_check and already_processed_check(msg_id):
                    logger.debug("Message %s already in database. Skipping fetch.", msg_id)
                    continue

                email_data = self.get_email_details(msg_id)
                if email_data:
                    parsed_emails.append(email_data)

            return parsed_emails
        except Exception as e:
            logger.error("Failed to fetch messages from Gmail: %s", e)
            return []

    def get_email_details(self, message_id: str) -> Optional[Dict[str, Any]]:
        """Fetch full details and body content for a specific Gmail message ID."""
        try:
            msg = self.service.users().messages().get(
                userId="me",
                id=message_id,
                format="full"
            ).execute()

            payload = msg.get("payload", {})
            headers_list = payload.get("headers", [])

            headers = {h["name"].lower(): h["value"] for h in headers_list}

            raw_from = headers.get("from", "")
            sender_name, sender_email = parseaddr(raw_from)
            if not sender_name:
                sender_name = sender_email.split("@")[0] if "@" in sender_email else "Sender"

            subject = headers.get("subject", "(No Subject)")
            date_str = headers.get("date", "")
            message_id_header = headers.get("message-id", "")
            references = headers.get("references", "")
            thread_id = msg.get("threadId", "")
            snippet = msg.get("snippet", "")

            # Extract body
            body_text = self._extract_body(payload)
            if not body_text.strip():
                body_text = snippet

            cleaned_body = self._clean_quoted_text(body_text)

            return {
                "gmail_message_id": message_id,
                "gmail_thread_id": thread_id,
                "message_id_header": message_id_header,
                "references": references,
                "sender_name": sender_name,
                "sender_email": sender_email,
                "subject": subject,
                "date": date_str,
                "snippet": snippet,
                "body": cleaned_body
            }
        except Exception as e:
            logger.error("Error retrieving message details for %s: %s", message_id, e)
            return None

    def mark_as_read(self, message_id: str):
        """Remove UNREAD label from processed email."""
        try:
            self.service.users().messages().modify(
                userId="me",
                id=message_id,
                body={"removeLabelIds": ["UNREAD"]}
            ).execute()
            logger.info("Marked message %s as read.", message_id)
        except Exception as e:
            logger.warning("Could not mark message %s as read: %s", message_id, e)

    def _extract_body(self, payload: Dict[str, Any]) -> str:
        """Recursively extract plain text or HTML body from Gmail message payload."""
        body = ""
        mime_type = payload.get("mimeType", "")

        # Direct body data
        if "body" in payload and "data" in payload["body"]:
            data_b64 = payload["body"]["data"]
            try:
                decoded = base64.urlsafe_b64decode(data_b64).decode("utf-8", errors="replace")
                if "html" in mime_type:
                    return self._strip_html(decoded)
                return decoded
            except Exception:
                pass

        # Multipart parts
        parts = payload.get("parts", [])
        for part in parts:
            part_mime = part.get("mimeType", "")
            if part_mime == "text/plain" and "data" in part.get("body", {}):
                try:
                    return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")
                except Exception:
                    pass
            elif part_mime == "text/html" and "data" in part.get("body", {}):
                try:
                    raw_html = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")
                    body = self._strip_html(raw_html)
                except Exception:
                    pass
            elif "parts" in part:
                sub_body = self._extract_body(part)
                if sub_body:
                    return sub_body

        return body

    def _strip_html(self, html_text: str) -> str:
        """Strip HTML tags and convert whitespace."""
        clean = re.sub(r"<style.*?</style>", "", html_text, flags=re.DOTALL)
        clean = re.sub(r"<script.*?</script>", "", clean, flags=re.DOTALL)
        clean = re.sub(r"<br\s*/?>", "\n", clean)
        clean = re.sub(r"</p>", "\n\n", clean)
        clean = re.sub(r"<[^>]+>", "", clean)
        return re.sub(r"\n\s*\n", "\n\n", clean).strip()

    def _clean_quoted_text(self, text: str) -> str:
        """Remove trailing email thread history (e.g., 'On Wed, ... wrote:')."""
        lines = text.split("\n")
        filtered_lines = []
        for line in lines:
            if re.match(r"^On\s+.*wrote:$", line.strip(), re.IGNORECASE):
                break
            if re.match(r"^-+\s*Original Message\s*-+", line.strip(), re.IGNORECASE):
                break
            if line.strip().startswith(">"):
                continue
            filtered_lines.append(line)

        return "\n".join(filtered_lines).strip()
