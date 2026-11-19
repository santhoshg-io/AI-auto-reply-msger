"""AI Decision Engine - Hybrid Automation Governor.

Evaluates an incoming email's semantic analysis against deterministic safety rules
and user policy to decide:
1. AUTOMATIC_REPLY (Safe routine emails when auto-reply is enabled)
2. APPROVAL_REQUIRED (Important, high-stakes, career, academic, or ambiguous emails)
3. DO_NOT_REPLY (Sensitive, security, financial, OTP, spam, or attack emails)
"""

import logging
from app.agent.models import EmailAnalysis, AutomationDecision, RiskLevel, AutomationMode
from app.config.settings import settings

logger = logging.getLogger(__name__)

# Categories that strictly require DO_NOT_REPLY (prevent accidental leaks or loops)
STRICT_NO_REPLY_CATEGORIES = {"Security Alert", "Financial", "Spam", "Newsletter", "Advertisement"}

# Categories that mandate human approval before sending
MANDATORY_APPROVAL_CATEGORIES = {"Job / Career", "Legal", "College / Academic", "General Enquiry"}


class DecisionEngine:
    """Evaluates emails and issues strict automation decisions."""

    def __init__(self, confidence_threshold: float = None):
        self.confidence_threshold = confidence_threshold or settings.MIN_CONFIDENCE_THRESHOLD

    def evaluate(self, analysis: EmailAnalysis) -> AutomationDecision:
        """Evaluate analysis and return an AutomationDecision."""

        # Rule 1: Prompt Injection / Adversarial Threat Quarantine
        if analysis.is_suspicious_or_attack:
            return AutomationDecision(
                decision="DO_NOT_REPLY",
                category=analysis.category,
                intent=analysis.intent,
                importance="High",
                risk_level="Critical",
                reply_required=False,
                reasoning="Adversarial prompt injection or security attack detected. Immediate quarantine.",
                confidence_score=analysis.confidence_score,
                safety_rule_triggered="RULE_PROMPT_INJECTION_DEFENSE"
            )

        # Rule 2: Sensitive Notifications (Security alerts, OTPs, Banking)
        if analysis.is_sensitive:
            if analysis.category in STRICT_NO_REPLY_CATEGORIES or "password" in analysis.intent.lower():
                return AutomationDecision(
                    decision="DO_NOT_REPLY",
                    category=analysis.category,
                    intent=analysis.intent,
                    importance=analysis.importance,
                    risk_level="High",
                    reply_required=False,
                    reasoning=f"Sensitive {analysis.category} email detected. Automated replies are strictly prohibited.",
                    confidence_score=analysis.confidence_score,
                    safety_rule_triggered="RULE_SENSITIVE_DATA_PROTECTION"
                )
            else:
                # Sensitive but sender is requesting input (e.g. Legal contract)
                return AutomationDecision(
                    decision="APPROVAL_REQUIRED",
                    category=analysis.category,
                    intent=analysis.intent,
                    importance="High",
                    risk_level="High",
                    reply_required=analysis.reply_required,
                    reasoning=f"Sensitive content in category '{analysis.category}'. Requires explicit human review.",
                    confidence_score=analysis.confidence_score,
                    safety_rule_triggered="RULE_SENSITIVE_APPROVAL_REQUIRED"
                )

        # Rule 3: Low AI Confidence Override
        if analysis.confidence_score < self.confidence_threshold:
            return AutomationDecision(
                decision="APPROVAL_REQUIRED",
                category=analysis.category,
                intent=analysis.intent,
                importance=analysis.importance,
                risk_level="Medium",
                reply_required=analysis.reply_required,
                reasoning=f"AI confidence score ({analysis.confidence_score:.2f}) is below threshold ({self.confidence_threshold:.2f}). Escalate to human.",
                confidence_score=analysis.confidence_score,
                safety_rule_triggered="RULE_LOW_CONFIDENCE_FALLBACK"
            )

        # Rule 4: Informational broadcasts (Newsletters, Spam, Announcements)
        if analysis.category in STRICT_NO_REPLY_CATEGORIES or not analysis.reply_required:
            return AutomationDecision(
                decision="DO_NOT_REPLY",
                category=analysis.category,
                intent=analysis.intent,
                importance=analysis.importance,
                risk_level="Low",
                reply_required=False,
                reasoning=f"Broadcast or {analysis.category} email requiring no response.",
                confidence_score=analysis.confidence_score,
                safety_rule_triggered="RULE_NO_REPLY_WARRANTED"
            )

        # Rule 5: High-Stakes Categories Mandating Human Approval
        if analysis.category in MANDATORY_APPROVAL_CATEGORIES:
            return AutomationDecision(
                decision="APPROVAL_REQUIRED",
                category=analysis.category,
                intent=analysis.intent,
                importance=analysis.importance,
                risk_level="Medium",
                reply_required=True,
                reasoning=f"Category '{analysis.category}' involves professional, academic, or legal commitments. Approval required.",
                confidence_score=analysis.confidence_score,
                safety_rule_triggered="RULE_HIGH_STAKES_APPROVAL"
            )

        # Rule 6: Safe Routine Automation (Meeting confirmations, simple queries)
        if settings.AUTO_REPLY_ENABLED:
            return AutomationDecision(
                decision="AUTOMATIC_REPLY",
                category=analysis.category,
                intent=analysis.intent,
                importance=analysis.importance,
                risk_level="Low",
                reply_required=True,
                reasoning="Safe routine email eligible for automatic reply under current user policy.",
                confidence_score=analysis.confidence_score,
                safety_rule_triggered="RULE_SAFE_AUTO_REPLY_GRANTED"
            )
        else:
            return AutomationDecision(
                decision="APPROVAL_REQUIRED",
                category=analysis.category,
                intent=analysis.intent,
                importance=analysis.importance,
                risk_level="Low",
                reply_required=True,
                reasoning="Email is safe for reply, but auto-reply is currently disabled in settings.",
                confidence_score=analysis.confidence_score,
                safety_rule_triggered="RULE_AUTO_REPLY_DISABLED"
            )
