"""Core Automation Orchestrator Service.

Coordinates Gmail email fetching, Groq semantic analysis, decision engine routing,
safe automatic reply dispatch, and persistent database audit logging.
"""

import logging
from datetime import datetime
from typing import Dict, Any, List
from sqlalchemy.orm import Session

from app.agent.email_analyzer import EmailAnalyzer
from app.agent.decision_engine import DecisionEngine
from app.agent.reply_generator import ReplyGenerator
from app.config.settings import settings
from app.database.repository import EmailRepository
from app.gmail.authentication import GmailAuthenticator
from app.gmail.email_fetcher import EmailFetcher
from app.gmail.email_sender import EmailSender

logger = logging.getLogger(__name__)


def is_automated_broadcast(sender_email: str, sender_name: str, subject: str) -> bool:
    """Identify automated notifications, system broadcasts, and no-reply bots.
    
    Prevents unnecessary Groq LLM API calls on emails that cannot receive replies.
    """
    lower_email = (sender_email or "").lower()
    lower_subj = (subject or "").lower()

    # 1. Standard No-Reply markers
    no_reply_markers = [
        "no-reply", "noreply", "donotreply", "do-not-reply",
        "mailer-daemon", "notifications@", "notification@",
        "bounce@", "broadcast@", "automated@", "system@", "alerts@"
    ]
    if any(marker in lower_email for marker in no_reply_markers):
        return True

    # 2. Known automated platform domains
    automated_domains = [
        "classroom.google.com", "accounts.google.com", "github.com",
        "youtube.com", "linkedin.com", "quora.com", "medium.com"
    ]
    if any(domain in lower_email for domain in automated_domains):
        return True

    # 3. Typical automated subject markers
    automated_subjects = [
        "security alert", "new announcement:", "notification settings",
        "password reset", "verify your email", "2-step verification"
    ]
    if any(subj in lower_subj for subj in automated_subjects):
        return True

    return False


class AutomationService:
    """Manages the full lifecycle of incoming email perception, reasoning, and automated dispatch."""

    def __init__(self, db: Session):
        self.db = db
        self.repo = EmailRepository(db)
        self.analyzer = EmailAnalyzer()
        self.decision_engine = DecisionEngine()
        self.reply_generator = ReplyGenerator()
        self.authenticator = GmailAuthenticator()

    def process_incoming_emails(self, max_emails: int = 10) -> Dict[str, Any]:
        """Fetch, analyze, and automatically handle incoming unread Gmail messages.
        
        Zero demo data: works strictly with the user's real Gmail messages.
        """
        if not self.authenticator.is_connected():
            return {
                "status": "error",
                "message": "Gmail is not connected. Authenticate with credentials.json or run authentication first."
            }

        gmail_service = self.authenticator.get_service()
        fetcher = EmailFetcher(gmail_service)
        sender = EmailSender(gmail_service)

        unread_emails = fetcher.fetch_unread_emails(
            max_results=max_emails,
            already_processed_check=self.repo.email_exists
        )
        if not unread_emails:
            return {
                "status": "success",
                "message": "No new unread emails in inbox.",
                "processed_count": 0
            }

        results = {
            "total_fetched": len(unread_emails),
            "auto_replied": 0,
            "pending_approval": 0,
            "do_not_reply": 0,
            "details": []
        }

        for email_data in unread_emails:
            gmail_msg_id = email_data["gmail_message_id"]

            try:
                # Step 1: Duplicate Processing Guard
                if self.repo.email_exists(gmail_msg_id):
                    logger.info("Email %s has already been processed. Skipping.", gmail_msg_id)
                    continue

                sender_name = email_data["sender_name"]
                sender_email = email_data["sender_email"]
                subject = email_data["subject"]
                body = email_data["body"]
                thread_id = email_data["gmail_thread_id"]
                msg_header_id = email_data.get("message_id_header", "")

                # Step 2: Heuristic Pre-Filter for Automated Broadcasts & No-Reply Senders
                # Saves API calls by never invoking Groq for non-replyable bots & notifications
                if is_automated_broadcast(sender_email, sender_name, subject):
                    fetcher.mark_as_read(gmail_msg_id)
                    self.repo.create_email_record(
                        gmail_message_id=gmail_msg_id,
                        gmail_thread_id=thread_id,
                        sender_name=sender_name,
                        sender_email=sender_email,
                        subject=subject,
                        snippet=email_data.get("snippet", ""),
                        body_text=body,
                        category="Newsletter",
                        intent="Automated platform notification / system announcement",
                        urgency="Low",
                        importance="Low",
                        risk_level="Low",
                        is_sensitive=False,
                        is_suspicious_or_attack=False,
                        reply_required=False,
                        confidence_score=1.0,
                        analysis_reasoning="Filtered locally without invoking AI agent (automated no-reply sender).",
                        status="ignored",
                        decision_reasoning="Automated broadcast/no-reply sender cannot receive email replies.",
                        safety_rule="RULE_AUTO_BROADCAST_NO_AI"
                    )
                    self.repo.log_action(
                        action="FILTERED_NO_AI",
                        details=f"Suppressed automated broadcast from {sender_email} (0 AI calls used)",
                        gmail_message_id=gmail_msg_id
                    )
                    results["do_not_reply"] += 1
                    continue

                # Step 3: Cognitive Perception (Groq AI) - ONLY FOR GENUINE EMAILS
                print(f"[+] Genuine new email from {sender_email}: '{subject}'. Invoking Groq AI agent...")
                analysis = self.analyzer.analyze(sender_name, sender_email, subject, body)

                # Step 4: Hybrid Automation Decision
                decision = self.decision_engine.evaluate(analysis)

                # Step 4: AI Reply Generation (for auto-reply or approval queue)
                generated_reply = None
                if decision.decision in ["AUTOMATIC_REPLY", "APPROVAL_REQUIRED"]:
                    try:
                        generated_reply = self.reply_generator.generate_reply(
                            sender_name=sender_name,
                            sender_email=sender_email,
                            subject=subject,
                            body=body,
                            analysis=analysis
                        )
                    except Exception as e:
                        logger.error("Reply generation failed for email %s: %s", gmail_msg_id, e)

                # Step 5: Execute Decision
                if decision.decision == "AUTOMATIC_REPLY" and generated_reply:
                    # Send the reply automatically via Gmail API
                    try:
                        sent_msg_id = sender.send_reply(
                            to_email=sender_email,
                            subject=generated_reply.subject,
                            reply_body=generated_reply.full_text,
                            thread_id=thread_id,
                            in_reply_to_header=msg_header_id
                        )

                        # Mark original email as read
                        fetcher.mark_as_read(gmail_msg_id)

                        # Persist record in database
                        self.repo.create_email_record(
                            gmail_message_id=gmail_msg_id,
                            gmail_thread_id=thread_id,
                            sender_name=sender_name,
                            sender_email=sender_email,
                            subject=subject,
                            snippet=email_data["snippet"],
                            body_text=body,
                            category=analysis.category,
                            intent=analysis.intent,
                            urgency=analysis.urgency,
                            importance=analysis.importance,
                            risk_level=decision.risk_level,
                            is_sensitive=analysis.is_sensitive,
                            is_suspicious_or_attack=analysis.is_suspicious_or_attack,
                            reply_required=analysis.reply_required,
                            confidence_score=decision.confidence_score,
                            analysis_reasoning=analysis.reasoning,
                            status="auto_replied",
                            decision_reasoning=decision.reasoning,
                            safety_rule=decision.safety_rule_triggered or "",
                            reply_subject=generated_reply.subject,
                            reply_body=generated_reply.full_text,
                            reply_tone=generated_reply.tone,
                            sent_message_id=sent_msg_id or "",
                            sent_at=datetime.utcnow()
                        )

                        self.repo.log_action(
                            action="AUTO_REPLIED",
                            details=f"Automatically sent reply to {sender_email} (Subject: {subject})",
                            gmail_message_id=gmail_msg_id
                        )

                        results["auto_replied"] += 1
                        results["details"].append({
                            "id": gmail_msg_id,
                            "action": "AUTO_REPLIED",
                            "sender": sender_email,
                            "subject": subject
                        })
                    except Exception as send_err:
                        logger.error("Failed to auto-reply to %s: %s", sender_email, send_err)

                elif decision.decision == "APPROVAL_REQUIRED":
                    # Save into Pending Approval queue for user review
                    self.repo.create_email_record(
                        gmail_message_id=gmail_msg_id,
                        gmail_thread_id=thread_id,
                        sender_name=sender_name,
                        sender_email=sender_email,
                        subject=subject,
                        snippet=email_data["snippet"],
                        body_text=body,
                        category=analysis.category,
                        intent=analysis.intent,
                        urgency=analysis.urgency,
                        importance=analysis.importance,
                        risk_level=decision.risk_level,
                        is_sensitive=analysis.is_sensitive,
                        is_suspicious_or_attack=analysis.is_suspicious_or_attack,
                        reply_required=analysis.reply_required,
                        confidence_score=decision.confidence_score,
                        analysis_reasoning=analysis.reasoning,
                        status="pending_approval",
                        decision_reasoning=decision.reasoning,
                        safety_rule=decision.safety_rule_triggered or "",
                        reply_subject=generated_reply.subject if generated_reply else f"Re: {subject}",
                        reply_body=generated_reply.full_text if generated_reply else "",
                        reply_tone=generated_reply.tone if generated_reply else settings.DEFAULT_REPLY_TONE
                    )

                    self.repo.log_action(
                        action="QUEUED_APPROVAL",
                        details=f"Queued email from {sender_email} for human approval ({analysis.category})",
                        gmail_message_id=gmail_msg_id
                    )

                    results["pending_approval"] += 1
                    results["details"].append({
                        "id": gmail_msg_id,
                        "action": "PENDING_APPROVAL",
                        "sender": sender_email,
                        "subject": subject
                    })

                else:  # DO_NOT_REPLY
                    status_label = "quarantined" if analysis.is_suspicious_or_attack else "ignored"
                    fetcher.mark_as_read(gmail_msg_id)

                    self.repo.create_email_record(
                        gmail_message_id=gmail_msg_id,
                        gmail_thread_id=thread_id,
                        sender_name=sender_name,
                        sender_email=sender_email,
                        subject=subject,
                        snippet=email_data["snippet"],
                        body_text=body,
                        category=analysis.category,
                        intent=analysis.intent,
                        urgency=analysis.urgency,
                        importance=analysis.importance,
                        risk_level=decision.risk_level,
                        is_sensitive=analysis.is_sensitive,
                        is_suspicious_or_attack=analysis.is_suspicious_or_attack,
                        reply_required=False,
                        confidence_score=decision.confidence_score,
                        analysis_reasoning=analysis.reasoning,
                        status=status_label,
                        decision_reasoning=decision.reasoning,
                        safety_rule=decision.safety_rule_triggered or ""
                    )

                    self.repo.log_action(
                        action="QUARANTINED" if analysis.is_suspicious_or_attack else "IGNORED",
                        details=f"Suppressed automated response for {sender_email} ({analysis.category}): {decision.reasoning}",
                        gmail_message_id=gmail_msg_id
                    )

                    results["do_not_reply"] += 1
                    results["details"].append({
                        "id": gmail_msg_id,
                        "action": status_label.upper(),
                        "sender": sender_email,
                        "subject": subject
                    })
            except Exception as item_err:
                logger.error("Error processing message %s: %s", gmail_msg_id, item_err)
                continue

        return results
