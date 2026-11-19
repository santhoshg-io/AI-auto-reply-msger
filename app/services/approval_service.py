"""Approval Workflow Service.

Handles human review actions:
- Approve and Send (dispatches reply immediately via Gmail)
- Edit and Send (saves modifications and dispatches)
- Regenerate Reply (calls Groq with new tone)
- Reject / Dismiss
"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session

from app.agent.reply_generator import ReplyGenerator
from app.agent.models import EmailAnalysis, ReplyTone
from app.database.repository import EmailRepository
from app.gmail.authentication import GmailAuthenticator
from app.gmail.email_sender import EmailSender
from app.gmail.email_fetcher import EmailFetcher

logger = logging.getLogger(__name__)


class ApprovalService:
    """Manages human-in-the-loop review operations."""

    def __init__(self, db: Session):
        self.db = db
        self.repo = EmailRepository(db)
        self.reply_generator = ReplyGenerator()
        self.authenticator = GmailAuthenticator()

    def approve_and_send(self, email_id: int, custom_reply_body: Optional[str] = None) -> Dict[str, Any]:
        """Approve a pending email and dispatch the reply via Gmail API."""
        record = self.repo.get_by_id(email_id)
        if not record:
            return {"success": False, "message": "Email record not found."}

        if record.status != "pending_approval":
            return {"success": False, "message": f"Email is already in status '{record.status}'."}

        if not self.authenticator.is_connected():
            return {"success": False, "message": "Gmail is not connected. Authenticate first."}

        service = self.authenticator.get_service()
        sender = EmailSender(service)
        fetcher = EmailFetcher(service)

        reply_to_send = custom_reply_body or record.reply_body
        if not reply_to_send:
            return {"success": False, "message": "No reply text available to send."}

        try:
            sent_id = sender.send_reply(
                to_email=record.sender_email,
                subject=record.reply_subject,
                reply_body=reply_to_send,
                thread_id=record.gmail_thread_id
            )

            # Mark original email as read in Gmail
            fetcher.mark_as_read(record.gmail_message_id)

            # Update database record
            self.repo.update_email_record(
                email_id=email_id,
                status="approved_and_sent",
                reply_body=reply_to_send,
                sent_message_id=sent_id or "",
                sent_at=datetime.utcnow()
            )

            self.repo.log_action(
                action="MANUALLY_APPROVED_AND_SENT",
                details=f"User approved and sent reply to {record.sender_email} (Subject: {record.subject})",
                gmail_message_id=record.gmail_message_id
            )

            return {
                "success": True,
                "message": f"Reply successfully sent to {record.sender_email}.",
                "sent_message_id": sent_id
            }
        except Exception as e:
            logger.error("Failed to send approved reply: %s", e)
            return {"success": False, "message": f"Gmail sending error: {str(e)}"}

    def regenerate_reply(self, email_id: int, new_tone: ReplyTone = "professional") -> Dict[str, Any]:
        """Regenerate reply text for a pending email using Groq with a specified tone."""
        record = self.repo.get_by_id(email_id)
        if not record:
            return {"success": False, "message": "Email record not found."}

        # Synthesize temporary analysis from stored fields
        analysis = EmailAnalysis(
            category=record.category,
            intent=record.intent,
            main_topic=record.subject,
            urgency=record.urgency,
            importance=record.importance,
            sentiment="Neutral",
            is_sensitive=record.is_sensitive,
            is_suspicious_or_attack=record.is_suspicious_or_attack,
            reply_required=record.reply_required,
            summary=record.snippet or record.subject,
            reasoning=record.analysis_reasoning or "",
            confidence_score=record.confidence_score
        )

        try:
            new_reply = self.reply_generator.generate_reply(
                sender_name=record.sender_name,
                sender_email=record.sender_email,
                subject=record.subject,
                body=record.body_text,
                analysis=analysis,
                preferred_tone=new_tone
            )

            self.repo.update_email_record(
                email_id=email_id,
                reply_body=new_reply.full_text,
                reply_tone=new_tone
            )

            self.repo.log_action(
                action="REGENERATED_REPLY",
                details=f"Regenerated reply for {record.sender_email} using tone '{new_tone}' via Groq",
                gmail_message_id=record.gmail_message_id
            )

            return {"success": True, "new_reply": new_reply.full_text, "tone": new_tone}
        except Exception as e:
            logger.error("Failed to regenerate reply via Groq: %s", e)
            return {"success": False, "message": f"Groq error: {str(e)}"}

    def reject(self, email_id: int, reason: str = "") -> Dict[str, Any]:
        """Reject a pending email reply (will not be sent)."""
        record = self.repo.get_by_id(email_id)
        if not record:
            return {"success": False, "message": "Email record not found."}

        self.repo.update_email_record(
            email_id=email_id,
            status="rejected",
            decision_reasoning=f"Rejected by user: {reason}" if reason else "Rejected by user."
        )

        self.repo.log_action(
            action="REJECTED_BY_USER",
            details=f"User rejected reply to {record.sender_email}: {reason}",
            gmail_message_id=record.gmail_message_id
        )

        return {"success": True, "message": "Email reply successfully rejected."}
