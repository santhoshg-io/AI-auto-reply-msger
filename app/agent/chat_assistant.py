"""AI Chatbot Assistant Component (Powered by Groq).

Interactive agent capable of:
1. Answering questions about inbox status, statistics, and emails.
2. Resolving contact roles (e.g., 'HOD', 'Class Teacher') from the database directory and prefilling emails.
3. Composing professional emails with strict academic etiquette ("Respected Sir / Dear Sir" only, no names).
"""

import json
import re
import logging
from typing import Dict, Any, List, Optional
from groq import Groq
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.database.repository import EmailRepository

logger = logging.getLogger(__name__)

CHAT_SYSTEM_PROMPT = """You are the personal AI Executive Assistant for {user_name} ({user_role}).
You chat with {user_name}, answer questions, and draft/send emails on their command.

USER PROFILE:
- Name: {user_name}
- Role: {user_role}

SAVED CONTACT DIRECTORY (Roles, Names, and Registered Emails):
{contacts_directory}

INBOX SUMMARY:
- Total Processed Emails: {total_processed}
- Automatically Replied: {auto_replied}
- Pending Approvals: {pending_approval}

MANDATORY INSTRUCTIONS FOR DRAFTING EMAILS:
1. AUTOMATIC CONTACT & EMAIL PREFILLING:
   - When {user_name} mentions any role, title, or alias (such as 'HOD', 'Class Teacher', 'Mentor', 'Principal'):
     * You MUST look up that role in the SAVED CONTACT DIRECTORY.
     * You MUST automatically PREFILL `recipient_email` with that role's exact registered email address from the directory.
     * If the user mentions attaching or CC'ing someone (e.g., 'attach class teacher', 'cc class teacher'), look up that role in the directory and automatically PREFILL `cc_emails` with their exact registered email address.
     * Never leave `recipient_email` empty if the role exists in the directory!

2. STRICT SALUTATION & ETIQUETTE RULE ("USE SIR ONLY, NO NAMES"):
   - In all professional and academic emails (to HOD, Professors, Class Teachers, Advisors, Management):
     * ALWAYS address the recipient as "Respected Sir," or "Dear Sir,".
     * NEVER USE THEIR PERSONAL NAMES in the greeting or body (NEVER write "Dear Ramesh", "Dear Dr. Ramesh", "Dear Priya", "Hi Priya").
     * USE "Sir" ONLY - NO NAMES IN SALUTATIONS.

3. EMAIL STRUCTURE & TONE:
   - Keep the tone polite, highly respectful, clear, and formal.
   - Standard structure:
     Respected Sir,

     [Clear statement of purpose: e.g., leave request with dates, reason, permission request]

     [Assurance of catching up on coursework or pending responsibilities]

     Thanking you,
     Yours respectfully,
     {user_name}

   - Set `"action": "SEND_EMAIL"`.

4. GENERAL CHAT / INQUIRIES:
   - If the user asks general questions, checks status, or chats, set `"action": "CHAT"` and answer helpfully.

OUTPUT FORMAT:
You MUST respond with a valid JSON object:
{{
  "action": "CHAT" | "SEND_EMAIL",
  "reply_message": "Friendly response to {user_name} explaining the drafted email and confirming the prefilled email addresses.",
  "email_draft": {{
    "recipient_name": "Role / Title (e.g. HOD)",
    "recipient_email": "exact_prefilled_email@college.edu",
    "cc_emails": "optional_prefilled_email@college.edu",
    "subject": "Clear Professional Subject",
    "body": "Respected Sir,\\n\\n[Email Body]...\\n\\nThanking you,\\nYours respectfully,\\n{user_name}"
  }}  // Set to null if action is "CHAT"
}}
"""


class ChatAssistant:
    """Conversational AI Assistant connected to Groq and the user's database."""

    def __init__(self, db: Session, repo: Optional[EmailRepository] = None):
        self.db = db
        self.repo = repo if repo is not None else EmailRepository(db)
        self.client = Groq(api_key=settings.GROQ_API_KEY) if settings.GROQ_API_KEY else None
        self.model = settings.GROQ_MODEL

    def _build_contacts_context(self) -> str:
        """Format saved contacts into text for LLM context."""
        try:
            contacts = self.repo.get_all_contacts()
        except AttributeError:
            from app.database.models import Contact
            contacts = self.db.query(Contact).order_by(Contact.role_alias.asc()).all()

        if not contacts:
            return "No contacts saved yet in directory. (User can add them in Contact Directory tab)."

        lines = []
        for c in contacts:
            lines.append(f"- Role/Alias: '{c.role_alias}', Full Name: '{c.full_name}', Email: <{c.email}>, Dept: '{c.department}'")
        return "\n".join(lines)

    def chat(self, user_message: str, chat_history: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
        """Process user message and return structured response or email draft."""
        if not self.client:
            return {
                "action": "CHAT",
                "reply_message": "GROQ_API_KEY is not set. Please add it to your .env file to enable the AI Chatbot.",
                "email_draft": None
            }

        stats = self.repo.get_statistics()
        contacts_str = self._build_contacts_context()

        system_content = CHAT_SYSTEM_PROMPT.format(
            user_name=settings.USER_NAME,
            user_role=settings.USER_ROLE,
            contacts_directory=contacts_str,
            total_processed=stats["total_processed"],
            auto_replied=stats["auto_replied"],
            pending_approval=stats["pending_approval"]
        )

        messages = [{"role": "system", "content": system_content}]

        # Append recent conversation history (last 6 messages)
        if chat_history:
            for turn in chat_history[-6:]:
                messages.append({"role": turn["role"], "content": turn["content"]})

        messages.append({"role": "user", "content": user_message})

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.3
            )

            raw_json = response.choices[0].message.content
            data = json.loads(raw_json)

            # Post-Processing Guards for Email Drafting
            if data.get("action") == "SEND_EMAIL" and data.get("email_draft"):
                draft = data["email_draft"]

                # 1. Guaranteed Role Email Resolution Fallback
                recip_email = (draft.get("recipient_email") or "").strip()
                if not recip_email or "@" not in recip_email:
                    for check_role in ["HOD", "Class Teacher", "Mentor", "Principal"]:
                        if check_role.lower() in user_message.lower():
                            c = self.repo.find_contact_by_role_or_name(check_role)
                            if c:
                                draft["recipient_email"] = c.email
                                draft["recipient_name"] = c.role_alias
                                break

                # 2. Guaranteed CC Email Resolution Fallback
                cc_email = (draft.get("cc_emails") or "").strip()
                if (not cc_email or "@" not in cc_email) and any(w in user_message.lower() for w in ["cc", "attach"]):
                    for check_role in ["class teacher", "hod", "mentor", "principal"]:
                        if check_role in user_message.lower() and check_role not in (draft.get("recipient_name", "")).lower():
                            c = self.repo.find_contact_by_role_or_name(check_role)
                            if c:
                                draft["cc_emails"] = c.email
                                break

                # 3. Enforcement of "Use Sir only, no names" in body
                body = draft.get("body", "")
                if body:
                    # Replace any name-based greetings like "Dear Dr. Ramesh,", "Dear Priya,", "Hi Mr. Kumar," with "Respected Sir,"
                    body = re.sub(
                        r'^(Dear|Hi|Hello)\s+(Dr\.?|Prof\.?|Mr\.?|Mrs\.?|Ms\.?)?\s*(?!(Sir|Madam)\b)[A-Za-z]+\s*[A-Za-z]*\s*,',
                        'Respected Sir,',
                        body,
                        flags=re.IGNORECASE
                    )
                    draft["body"] = body

            return data

        except Exception as e:
            logger.error("Chat assistant error: %s", e)
            return {
                "action": "CHAT",
                "reply_message": f"Error consulting AI Assistant: {str(e)}",
                "email_draft": None
            }
