"""AI Automatic Email Reply Agent - Streamlit Dashboard.

Displays live database statistics, email review queues, audit logs,
interactive AI Chatbot with contact role resolution, and Contact Directory.
Zero mock/demo data: operates strictly against the live SQLite database & Groq.
"""

import sys
from pathlib import Path
from datetime import datetime
import pandas as pd

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir))

import importlib
import app.database.models
import app.database.repository
import app.agent.chat_assistant
import app.gmail.email_sender
import app.gmail.authentication
import app.services.automation_service
import app.services.approval_service

# Ensure live module definitions are reloaded in long-running Streamlit processes
importlib.reload(app.database.models)
importlib.reload(app.database.repository)
importlib.reload(app.agent.chat_assistant)
importlib.reload(app.gmail.email_sender)
importlib.reload(app.gmail.authentication)
importlib.reload(app.services.automation_service)
importlib.reload(app.services.approval_service)

import streamlit as st
from app.config.settings import settings
from app.database.connection import init_db, SessionLocal
from app.database.repository import EmailRepository
from app.gmail.authentication import GmailAuthenticator
from app.gmail.email_sender import EmailSender
from app.agent.chat_assistant import ChatAssistant
from app.services.automation_service import AutomationService
from app.services.approval_service import ApprovalService

# Ensure database tables exist
init_db()

st.set_page_config(
    page_title="AI Email Agent - Hybrid Mode",
    page_icon="✉️",
    layout="wide"
)

# Custom header styling
st.markdown("""
<style>
    .metric-card {
        background-color: #f8f9fa;
        border-radius: 8px;
        padding: 16px;
        border-left: 5px solid #4CAF50;
    }
    .stChatMessage {
        border-radius: 8px;
        margin-bottom: 8px;
    }
</style>
""", unsafe_allow_html=True)


def get_db_session():
    return SessionLocal()


# Top Bar
col_title, col_sync, col_status = st.columns([3, 1, 1])
with col_title:
    st.title("✉️ AI Automatic Email Reply Agent")
    st.caption(f"Powered by **Groq ({settings.GROQ_MODEL})** | Owner: **{settings.USER_NAME}** ({settings.USER_ROLE})")

authenticator = GmailAuthenticator()
is_connected = authenticator.is_connected()

with col_status:
    if is_connected:
        st.success("🟢 Gmail Connected")
    else:
        st.warning("🔴 Gmail Disconnected")

with col_sync:
    if st.button("🔄 Sync Inbox Now", type="primary"):
        with st.spinner("Checking for unread actionable emails & running Groq AI pipeline..."):
            db = get_db_session()
            try:
                service = AutomationService(db)
                result = service.process_incoming_emails()
                if result.get("status") == "error":
                    st.error(result.get("message"))
                else:
                    st.success(
                        f"Inbox synced! Auto-replied: {result.get('auto_replied', 0)}, "
                        f"Pending: {result.get('pending_approval', 0)}"
                    )
            finally:
                db.close()
            st.rerun()

st.divider()

# Navigation tabs
tabs = st.tabs([
    "💬 AI Assistant",
    "👥 Contact Directory",
    "📊 Overview",
    "⏳ Pending Approval",
    "⚡ Automatically Replied",
    "📥 All Emails",
    "📜 Activity Logs",
    "⚙️ Settings & Connection"
])

db = get_db_session()
repo = EmailRepository(db)

# ==============================================================================
# TAB 1: 💬 AI CHATBOT ASSISTANT
# ==============================================================================
with tabs[0]:
    st.subheader("💬 Interactive AI Email & Inbox Assistant")
    st.caption(
        "Chat with your AI assistant to query your inbox status or ask it to compose and dispatch emails. "
        "It automatically resolves saved roles like **'HOD'** or **'Class Teacher'** and CCs them!"
    )

    # Initialize chat session history
    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = [
            {
                "role": "assistant",
                "content": f"Hello {settings.USER_NAME}! I'm your AI Email Assistant powered by Groq. "
                           f"You can ask me questions about your inbox or tell me to send an email "
                           f"(e.g., *'Send mail to HOD asking for 2 days leave for medical reasons, attach class teacher'*). "
                           f"How can I assist you today?"
            }
        ]

    # Quick prompt buttons
    st.markdown("**Quick Prompts:**")
    qp1, qp2, qp3, qp4 = st.columns(4)
    quick_input = None
    if qp1.button("📝 Leave request to HOD (cc Teacher)"):
        quick_input = "Send mail to HOD asking for 2 days leave due to fever, attach class teacher"
    if qp2.button("📊 Summarize inbox status"):
        quick_input = "Give me a summary of my inbox status and pending emails."
    if qp3.button("👥 List my registered contacts"):
        quick_input = "What contacts and roles do I have saved in my directory?"
    if qp4.button("🗑️ Clear Chat History"):
        st.session_state.chat_messages = []
        st.rerun()

    # Display conversation history
    for idx, msg in enumerate(st.session_state.chat_messages):
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

            # If there's an email draft attached to this assistant message
            if msg.get("email_draft"):
                draft = msg["email_draft"]
                draft_id = f"draft_{idx}"

                with st.container(border=True):
                    st.markdown("### ✉️ Generated Email Draft")
                    col_d1, col_d2 = st.columns(2)
                    with col_d1:
                        to_val = st.text_input("To (Recipient)", value=draft.get("recipient_email", ""), key=f"to_{draft_id}")
                    with col_d2:
                        cc_val = st.text_input("CC (Optional)", value=draft.get("cc_emails") or "", key=f"cc_{draft_id}")

                    subj_val = st.text_input("Subject", value=draft.get("subject", ""), key=f"subj_{draft_id}")
                    body_val = st.text_area("Body", value=draft.get("body", ""), height=180, key=f"body_{draft_id}")

                    if msg.get("is_sent"):
                        st.success(f"✅ Dispatched via Gmail API! Message ID: `{msg.get('sent_message_id', 'Sent')}`")
                    else:
                        if st.button("🚀 Send Email via Gmail Now", key=f"send_btn_{draft_id}", type="primary"):
                            if not is_connected:
                                st.error("Gmail is not connected. Please authenticate in the 'Settings & Connection' tab.")
                            elif not to_val.strip():
                                st.error("Please enter a valid recipient email address.")
                            else:
                                with st.spinner("Dispatching email via Gmail API..."):
                                    try:
                                        gmail_svc = authenticator.get_service()
                                        sender = EmailSender(gmail_svc)
                                        if not hasattr(sender, "send_new_email"):
                                            import app.gmail.email_sender
                                            importlib.reload(app.gmail.email_sender)
                                            from app.gmail.email_sender import EmailSender as FreshEmailSender
                                            sender = FreshEmailSender(gmail_svc)

                                        sent_id = sender.send_new_email(
                                            to_email=to_val.strip(),
                                            subject=subj_val.strip(),
                                            body=body_val.strip(),
                                            cc_emails=cc_val.strip() if cc_val.strip() else None
                                        )
                                        repo.log_action(
                                            action="AI_CHAT_NEW_EMAIL_SENT",
                                            details=f"Sent email to {to_val.strip()} (CC: {cc_val.strip()}) - Subj: {subj_val[:40]}"
                                        )
                                        msg["is_sent"] = True
                                        msg["sent_message_id"] = sent_id
                                        st.success(f"🎉 Email successfully delivered via Gmail! Message ID: `{sent_id}`")
                                        st.rerun()
                                    except Exception as send_err:
                                        st.error(f"Failed to send email: {send_err}")

    # Handle user text input
    user_query = st.chat_input("Ask a question or say: 'Send mail to HOD asking for leave, cc class teacher'...")
    prompt_to_process = quick_input or user_query

    if prompt_to_process:
        # Add user message to history
        st.session_state.chat_messages.append({"role": "user", "content": prompt_to_process})

        with st.spinner("AI Assistant is thinking with Groq..."):
            assistant = ChatAssistant(db, repo=repo)
            # Pass history without email_draft objects
            clean_history = [
                {"role": m["role"], "content": m["content"]}
                for m in st.session_state.chat_messages[:-1]
            ]
            response = assistant.chat(prompt_to_process, chat_history=clean_history)

            action = response.get("action", "CHAT")
            reply_msg = response.get("reply_message", "Here is what I found.")
            email_draft = response.get("email_draft")

            st.session_state.chat_messages.append({
                "role": "assistant",
                "content": reply_msg,
                "email_draft": email_draft if action == "SEND_EMAIL" else None,
                "is_sent": False
            })

        st.rerun()

# ==============================================================================
# TAB 2: 👥 CONTACT DIRECTORY
# ==============================================================================
with tabs[1]:
    st.subheader("👥 Contact & Role Directory")
    st.markdown(
        "Register key roles and people here (e.g. **HOD**, **Class Teacher**, **Mentor**, **Principal**). "
        "When you chat with the AI and say *'Send mail to HOD, attach class teacher'*, "
        "the AI automatically looks up their email addresses from this directory!"
    )

    contacts = repo.get_all_contacts()

    col_form, col_list = st.columns([1, 1.4], gap="large")

    with col_form:
        st.markdown("### ➕ Add or Update Contact")
        with st.form("contact_form", clear_on_submit=True):
            role_alias = st.text_input("Role / Alias * (e.g. HOD, Class Teacher, Mentor)", placeholder="HOD")
            full_name = st.text_input("Full Name", placeholder="Dr. Ramesh Kumar")
            email = st.text_input("Email Address *", placeholder="hod.cse@college.edu")
            dept = st.text_input("Department / Section", placeholder="Computer Science & Engineering")
            notes = st.text_input("Notes / Responsibilities", placeholder="Handles department approvals, leave requests")

            submitted = st.form_submit_button("💾 Save to Directory", type="primary")
            if submitted:
                if not role_alias.strip() or not email.strip():
                    st.error("Role/Alias and Email Address are required.")
                else:
                    repo.add_contact(
                        role_alias=role_alias.strip(),
                        full_name=full_name.strip(),
                        email=email.strip(),
                        department=dept.strip(),
                        notes=notes.strip()
                    )
                    st.success(f"Saved contact for '{role_alias.strip()}'!")
                    st.rerun()

        # Seed pre-fill helper
        st.markdown("---")
        st.markdown("**Need a quick setup?**")
        if st.button("⚡ Pre-fill Sample College Contacts (HOD, Class Teacher, Mentor)"):
            repo.add_contact(
                role_alias="HOD",
                full_name="Dr. Ramesh Kumar",
                email="hod.cse@college.edu",
                department="Computer Science",
                notes="Head of Department - handles official permissions & leave requests"
            )
            repo.add_contact(
                role_alias="Class Teacher",
                full_name="Mrs. Priya Sundaram",
                email="priya.cse@college.edu",
                department="Computer Science",
                notes="Class Advisor / Teacher - monitors attendance & daily coursework"
            )
            repo.add_contact(
                role_alias="Mentor",
                full_name="Prof. Anand",
                email="anand.mentor@college.edu",
                department="Computer Science",
                notes="Faculty Mentor - project guidance & academic advice"
            )
            st.success("Pre-filled college contacts! You can edit or delete them anytime.")
            st.rerun()

    with col_list:
        st.markdown(f"### 📋 Saved Directory ({len(contacts)} contacts)")

        if not contacts:
            st.info("No contacts saved yet. Use the form on the left or click 'Pre-fill Sample College Contacts' to add some.")
        else:
            for c in contacts:
                with st.container(border=True):
                    head_col, del_col = st.columns([4, 1])
                    with head_col:
                        st.markdown(f"**🏷️ Role / Alias:** `{c.role_alias}`")
                        st.markdown(f"👤 **{c.full_name or 'N/A'}** &lt;[`{c.email}`](mailto:{c.email})&gt;")
                        if c.department:
                            st.caption(f"🏢 Dept: {c.department}")
                        if c.notes:
                            st.caption(f"📝 Notes: {c.notes}")
                    with del_col:
                        if st.button("🗑️ Delete", key=f"del_c_{c.id}"):
                            repo.delete_contact(c.id)
                            st.info(f"Deleted contact {c.role_alias}.")
                            st.rerun()

# ==============================================================================
# TAB 3: 📊 OVERVIEW
# ==============================================================================
with tabs[2]:
    stats = repo.get_statistics()
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Total Processed", stats["total_processed"])
    m2.metric("Automatically Replied", stats["auto_replied"])
    m3.metric("Pending Approval", stats["pending_approval"])
    m4.metric("Approved & Sent", stats["approved_and_sent"])
    m5.metric("Ignored / Quarantined", stats["ignored_or_quarantined"])

    st.subheader("System Status")
    c1, c2, c3 = st.columns(3)
    c1.info(f"**Auto-Reply Mode:** {'Enabled' if settings.AUTO_REPLY_ENABLED else 'Disabled'}")
    c2.info(f"**Confidence Threshold:** {settings.MIN_CONFIDENCE_THRESHOLD:.0%}")
    c3.info(f"**Default Reply Tone:** {settings.DEFAULT_REPLY_TONE.capitalize()}")

    st.subheader("Recent Agent Activity")
    recent_emails = repo.get_all_emails(limit=5)
    if not recent_emails:
        st.info("No emails processed yet. Connect Gmail and click 'Sync Inbox Now'.")
    else:
        for em in recent_emails:
            with st.expander(f"[{em.status.upper()}] {em.subject} - {em.sender_email}"):
                st.write(f"**Category:** {em.category} | **Intent:** {em.intent}")
                st.write(f"**Confidence:** {em.confidence_score:.2f} | **Risk:** {em.risk_level}")
                st.write(f"**Snippet:** {em.snippet}")

# ==============================================================================
# TAB 4: ⏳ PENDING APPROVAL
# ==============================================================================
with tabs[3]:
    st.subheader("Emails Awaiting Human Approval")
    pending = repo.get_pending_approvals()

    if not pending:
        st.success("✅ No emails currently pending approval. All caught up!")
    else:
        approval_service = ApprovalService(db)
        for em in pending:
            with st.container(border=True):
                st.markdown(f"### {em.subject}")
                st.caption(f"From: **{em.sender_name}** (`{em.sender_email}`) | Received: {em.created_at.strftime('%Y-%m-%d %H:%M')}")

                col_meta1, col_meta2, col_meta3 = st.columns(3)
                col_meta1.write(f"**Category:** `{em.category}`")
                col_meta2.write(f"**Urgency:** `{em.urgency}`")
                col_meta3.write(f"**Confidence:** `{em.confidence_score:.2f}`")

                st.write(f"**AI Intent:** {em.intent}")
                st.write(f"**Why Approval Required:** {em.decision_reasoning}")

                st.markdown("**Original Email:**")
                st.text_area("Original Content", em.body_text or em.snippet, height=120, disabled=True, key=f"orig_{em.id}")

                st.markdown("**Proposed AI Reply (Drafted with Groq):**")
                reply_edit = st.text_area("Reply Draft", em.reply_body, height=140, key=f"reply_{em.id}")

                btn_col1, btn_col2, btn_col3, btn_col4 = st.columns([1.5, 1.5, 1.5, 1])

                with btn_col1:
                    if st.button("🚀 Approve & Send", key=f"app_{em.id}", type="primary"):
                        with st.spinner("Dispatching reply via Gmail API..."):
                            res = approval_service.approve_and_send(em.id, custom_reply_body=reply_edit)
                            if res["success"]:
                                st.success(res["message"])
                                st.rerun()
                            else:
                                st.error(res["message"])

                with btn_col2:
                    new_tone = st.selectbox("Tone", ["professional", "friendly", "formal", "concise"], key=f"tone_{em.id}")
                    if st.button("🔄 Regenerate", key=f"regen_{em.id}"):
                        with st.spinner("Regenerating reply with Groq..."):
                            res = approval_service.regenerate_reply(em.id, new_tone=new_tone)
                            if res["success"]:
                                st.rerun()
                            else:
                                st.error(res["message"])

                with btn_col3:
                    if st.button("❌ Reject / Ignore", key=f"rej_{em.id}"):
                        approval_service.reject(em.id, reason="Dismissed by user in dashboard")
                        st.info("Email rejected.")
                        st.rerun()

# ==============================================================================
# TAB 5: ⚡ AUTOMATICALLY REPLIED
# ==============================================================================
with tabs[4]:
    st.subheader("⚡ Automatically Replied Emails")
    auto_replied = repo.get_auto_replied()

    if not auto_replied:
        st.info("No emails have been replied to automatically yet.")
    else:
        for em in auto_replied:
            with st.expander(f"✅ {em.subject} -> {em.sender_email} ({em.sent_at.strftime('%Y-%m-%d %H:%M') if em.sent_at else 'Sent'})"):
                st.write(f"**Category:** {em.category} | **Rule:** `{em.safety_rule}`")
                st.write(f"**Intent:** {em.intent}")
                st.markdown("**Sent Reply:**")
                st.info(em.reply_body)

# ==============================================================================
# TAB 6: 📥 ALL EMAILS
# ==============================================================================
with tabs[5]:
    st.subheader("All Processed Emails")
    all_emails = repo.get_all_emails(limit=100)
    if not all_emails:
        st.info("No emails in database.")
    else:
        for em in all_emails:
            with st.expander(f"[{em.status.upper()}] {em.subject} - {em.sender_email}"):
                st.write(f"**ID:** {em.id} | **Gmail ID:** `{em.gmail_message_id}`")
                st.write(f"**Category:** {em.category} | **Intent:** {em.intent}")
                st.write(f"**Risk Level:** {em.risk_level} | **Sensitive:** {em.is_sensitive}")
                st.write(f"**Reasoning:** {em.decision_reasoning}")
                if em.reply_body:
                    st.text_area("Reply Content", em.reply_body, height=100, disabled=True, key=f"all_{em.id}")

# ==============================================================================
# TAB 7: 📜 ACTIVITY LOGS
# ==============================================================================
with tabs[6]:
    st.subheader("Agent Audit Trail")
    logs = repo.get_logs(limit=100)
    if not logs:
        st.info("No activity logs recorded yet.")
    else:
        for log in logs:
            st.text(f"[{log.timestamp.strftime('%Y-%m-%d %H:%M:%S')}] [{log.action}] {log.details}")

# ==============================================================================
# TAB 8: ⚙️ SETTINGS & CONNECTION
# ==============================================================================
with tabs[7]:
    st.subheader("Gmail OAuth 2.0 Connection")
    if is_connected:
        st.success("Your Gmail account is currently authenticated and ready.")
        if st.button("Disconnect Account"):
            token_path = Path(settings.GMAIL_TOKEN_FILE)
            if token_path.exists():
                token_path.unlink()
                st.info("Token file removed. Disconnected.")
                st.rerun()
    else:
        st.warning("Gmail is not yet connected.")
        st.markdown(f"""
        **How to connect:**
        1. Place your Google Cloud OAuth client credentials in `{settings.GMAIL_CREDENTIALS_FILE}`.
        2. Run `python run_agent.py --auth` in your terminal to complete Google sign-in.
        """)

    st.divider()
    st.subheader("AI Agent Configuration")
    st.write(f"• **AI Provider:** Groq")
    st.write(f"• **Groq Model:** `{settings.GROQ_MODEL}`")
    st.write(f"• **Automatic Reply Enabled:** `{settings.AUTO_REPLY_ENABLED}`")
    st.write(f"• **Owner Name:** `{settings.USER_NAME}`")
    st.write(f"• **Owner Role:** `{settings.USER_ROLE}`")

db.close()
