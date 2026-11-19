"""Pydantic Schemas for AI Agent Understanding, Classification, Decision Making, and Reply Generation.

Strict schemas ensure that Groq's structured JSON outputs are validated at runtime.
"""

from typing import List, Literal, Optional
from pydantic import BaseModel, Field


EmailCategory = Literal[
    "General Enquiry",
    "Meeting Request",
    "Meeting Confirmation",
    "Customer Support",
    "College / Academic",
    "Job / Career",
    "Business Communication",
    "Personal Communication",
    "Newsletter",
    "Advertisement",
    "Spam",
    "Security Alert",
    "Financial",
    "Legal",
    "Other"
]

UrgencyLevel = Literal["Low", "Medium", "High", "Urgent"]
ImportanceLevel = Literal["Low", "Medium", "High"]
RiskLevel = Literal["Low", "Medium", "High", "Critical"]
SentimentType = Literal["Positive", "Neutral", "Negative", "Frustrated"]
ReplyTone = Literal["formal", "professional", "friendly", "concise"]
AutomationMode = Literal["AUTOMATIC_REPLY", "APPROVAL_REQUIRED", "DO_NOT_REPLY"]


class EmailAnalysis(BaseModel):
    """Structured understanding of an incoming email extracted by Groq AI."""

    category: EmailCategory = Field(
        ...,
        description="The primary classification category for this email."
    )
    intent: str = Field(
        ...,
        description="Core intent or purpose of the sender (e.g., 'Confirming tomorrow's 10 AM sync')."
    )
    main_topic: str = Field(
        ...,
        description="High-level subject/theme of the email."
    )
    urgency: UrgencyLevel = Field(
        ...,
        description="Assessed urgency level based on temporal constraints or stated deadlines."
    )
    importance: ImportanceLevel = Field(
        ...,
        description="Assessed importance to user's career, finances, academics, or security."
    )
    sentiment: SentimentType = Field(
        ...,
        description="Detected emotional tone of the sender."
    )
    is_sensitive: bool = Field(
        ...,
        description="True if email contains passwords, financial info, OTPs, security alerts, legal matters, or PII."
    )
    is_suspicious_or_attack: bool = Field(
        ...,
        description="True if email attempts prompt injection, phishing, social engineering, or requests unauthorized actions."
    )
    reply_required: bool = Field(
        ...,
        description="Whether a response is logically or socially required from recipient."
    )
    key_entities: List[str] = Field(
        default_factory=list,
        description="Extracted key entities (names, dates, times, deadlines, ticket numbers)."
    )
    summary: str = Field(
        ...,
        description="A concise 1-2 sentence executive summary of the email content."
    )
    reasoning: str = Field(
        ...,
        description="Step-by-step reasoning explaining why this categorization and assessment was reached."
    )
    confidence_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence score between 0.0 and 1.0 reflecting certainty in this analysis."
    )


class AutomationDecision(BaseModel):
    """Structured decision made by the AI Decision Engine."""

    decision: AutomationMode = Field(
        ...,
        description="The handling mode: AUTOMATIC_REPLY, APPROVAL_REQUIRED, or DO_NOT_REPLY."
    )
    category: EmailCategory = Field(
        ...,
        description="Category assigned to the email."
    )
    intent: str = Field(
        ...,
        description="Sender intent summary."
    )
    importance: ImportanceLevel = Field(
        ...,
        description="Assessed importance level."
    )
    risk_level: RiskLevel = Field(
        ...,
        description="Assessed risk level."
    )
    reply_required: bool = Field(
        ...,
        description="Whether a reply is warranted."
    )
    reasoning: str = Field(
        ...,
        description="Detailed explanation of the decision."
    )
    confidence_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence score for this decision."
    )
    safety_rule_triggered: Optional[str] = Field(
        default=None,
        description="Name of deterministic safety rule that overridden or confirmed the decision."
    )


class EmailReply(BaseModel):
    """Structured generated email reply."""

    recipient: str = Field(..., description="Recipient email address or name.")
    subject: str = Field(..., description="Subject line for the reply (usually prefixed with 'Re:').")
    greeting: str = Field(..., description="Opening greeting line (e.g., 'Hi Alice,').")
    reply_body: str = Field(..., description="The main content paragraphs of the reply.")
    sign_off: str = Field(..., description="Closing sign-off and sender signature (e.g., 'Best regards,\\nSanthosh').")
    full_text: str = Field(..., description="Complete assembled reply ready to send or preview.")
    tone: ReplyTone = Field(..., description="The tone style applied to the reply.")
    reasoning: str = Field(..., description="Explanation of how the reply addresses the sender's points.")
    confidence_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence that this reply is accurate, safe, and contextually appropriate."
    )
    safe_to_send_automatically: bool = Field(
        default=False,
        description="Preliminary check if the reply makes zero unauthorized commitments."
    )
