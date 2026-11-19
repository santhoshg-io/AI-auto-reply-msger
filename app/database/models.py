"""SQLAlchemy Database Models for Persistent Agent Memory."""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Float, Boolean, DateTime
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class ProcessedEmail(Base):
    """Stores every email inspected, analyzed, and handled by the agent."""
    __tablename__ = "processed_emails"

    id = Column(Integer, primary_key=True, autoincrement=True)
    gmail_message_id = Column(String(100), unique=True, index=True, nullable=False)
    gmail_thread_id = Column(String(100), index=True, nullable=False)
    sender_name = Column(String(200), default="")
    sender_email = Column(String(200), index=True, nullable=False)
    subject = Column(String(500), default="")
    snippet = Column(Text, default="")
    body_text = Column(Text, default="")

    # AI Cognitive Analysis
    category = Column(String(100), default="Other")
    intent = Column(String(300), default="")
    urgency = Column(String(50), default="Low")
    importance = Column(String(50), default="Low")
    risk_level = Column(String(50), default="Low")
    is_sensitive = Column(Boolean, default=False)
    is_suspicious_or_attack = Column(Boolean, default=False)
    reply_required = Column(Boolean, default=False)
    confidence_score = Column(Float, default=0.0)
    analysis_reasoning = Column(Text, default="")

    # Handling Status: pending_approval | auto_replied | approved_and_sent | rejected | ignored | quarantined
    status = Column(String(50), index=True, default="pending_approval")
    decision_reasoning = Column(Text, default="")
    safety_rule = Column(String(100), default="")

    # Reply Information
    reply_subject = Column(String(500), default="")
    reply_body = Column(Text, default="")
    reply_tone = Column(String(50), default="professional")
    sent_message_id = Column(String(100), default="")
    sent_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AgentLog(Base):
    """Audit trail for every action taken by the AI agent."""
    __tablename__ = "agent_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    action = Column(String(100), nullable=False)  # e.g., FETCHED, ANALYZED, AUTO_REPLIED, QUEUED_APPROVAL, SENT
    gmail_message_id = Column(String(100), default="")
    details = Column(Text, default="")
    level = Column(String(20), default="INFO")
    timestamp = Column(DateTime, default=datetime.utcnow)


class Contact(Base):
    """Directory of known roles & contacts (e.g. HOD, Class Teacher, Mentor)."""
    __tablename__ = "contacts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    role_alias = Column(String(100), index=True, nullable=False)  # e.g., "HOD", "Class Teacher"
    full_name = Column(String(200), default="")
    email = Column(String(200), index=True, nullable=False)
    department = Column(String(100), default="")
    notes = Column(String(300), default="")
    created_at = Column(DateTime, default=datetime.utcnow)
