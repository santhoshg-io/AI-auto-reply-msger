"""Unit Tests for Groq Email Analyzer, Decision Engine, and Reply Generator."""

import pytest
from unittest.mock import MagicMock, patch
from app.agent.email_analyzer import EmailAnalyzer
from app.agent.reply_generator import ReplyGenerator
from app.agent.decision_engine import DecisionEngine
from app.agent.models import EmailAnalysis


@pytest.fixture
def sample_analysis_safe():
    return EmailAnalysis(
        category="Meeting Confirmation",
        intent="Confirming tomorrow's 10:00 AM sync",
        main_topic="Sync Meeting Confirmation",
        urgency="Medium",
        importance="Medium",
        sentiment="Positive",
        is_sensitive=False,
        is_suspicious_or_attack=False,
        reply_required=True,
        key_entities=["Tomorrow 10:00 AM"],
        summary="Sender wants to confirm 10:00 AM sync.",
        reasoning="Routine meeting confirmation.",
        confidence_score=0.95
    )


@pytest.fixture
def sample_analysis_attack():
    return EmailAnalysis(
        category="Spam",
        intent="Adversarial system override",
        main_topic="Prompt Injection Threat",
        urgency="Urgent",
        importance="High",
        sentiment="Negative",
        is_sensitive=True,
        is_suspicious_or_attack=True,
        reply_required=False,
        key_entities=["SuperAdmin"],
        summary="Adversarial prompt injection attempt.",
        reasoning="Overrides system instructions.",
        confidence_score=0.99
    )


def test_decision_engine_safe_auto_reply(sample_analysis_safe):
    """Verify that a routine meeting sync is eligible for automatic reply."""
    engine = DecisionEngine(confidence_threshold=0.75)
    decision = engine.evaluate(sample_analysis_safe)

    assert decision.decision == "AUTOMATIC_REPLY"
    assert decision.risk_level == "Low"
    assert decision.safety_rule_triggered == "RULE_SAFE_AUTO_REPLY_GRANTED"


def test_decision_engine_attack_quarantine(sample_analysis_attack):
    """Verify that prompt injection attacks strictly result in DO_NOT_REPLY with critical risk."""
    engine = DecisionEngine()
    decision = engine.evaluate(sample_analysis_attack)

    assert decision.decision == "DO_NOT_REPLY"
    assert decision.risk_level == "Critical"
    assert decision.safety_rule_triggered == "RULE_PROMPT_INJECTION_DEFENSE"


def test_decision_engine_sensitive_notification():
    """Verify that financial notices and OTPs are not replied to."""
    analysis_fin = EmailAnalysis(
        category="Financial",
        intent="Monthly account statement",
        main_topic="Bank e-Statement",
        urgency="Low",
        importance="High",
        sentiment="Neutral",
        is_sensitive=True,
        is_suspicious_or_attack=False,
        reply_required=False,
        key_entities=["Global Bank"],
        summary="Monthly statement is available.",
        reasoning="Confidential financial statement.",
        confidence_score=0.98
    )

    engine = DecisionEngine()
    decision = engine.evaluate(analysis_fin)

    assert decision.decision == "DO_NOT_REPLY"
    assert decision.safety_rule_triggered == "RULE_SENSITIVE_DATA_PROTECTION"


def test_decision_engine_low_confidence_fallback():
    """Verify that emails with confidence below threshold are escalated to human approval."""
    analysis_vague = EmailAnalysis(
        category="Personal Communication",
        intent="Vague inquiry without context",
        main_topic="Unknown topic",
        urgency="Low",
        importance="Low",
        sentiment="Neutral",
        is_sensitive=False,
        is_suspicious_or_attack=False,
        reply_required=True,
        key_entities=[],
        summary="Vague follow-up.",
        reasoning="Missing contextual information.",
        confidence_score=0.55
    )

    engine = DecisionEngine(confidence_threshold=0.75)
    decision = engine.evaluate(analysis_vague)

    assert decision.decision == "APPROVAL_REQUIRED"
    assert decision.safety_rule_triggered == "RULE_LOW_CONFIDENCE_FALLBACK"


def test_decision_engine_high_stakes_approval():
    """Verify that job interviews mandate human approval."""
    analysis_job = EmailAnalysis(
        category="Job / Career",
        intent="Invitation to interview for Senior AI Engineer",
        main_topic="Technical Interview Invitation",
        urgency="High",
        importance="High",
        sentiment="Positive",
        is_sensitive=False,
        is_suspicious_or_attack=False,
        reply_required=True,
        key_entities=["InnovaTech"],
        summary="Recruiter invites user for interview.",
        reasoning="High-stakes professional opportunity.",
        confidence_score=0.95
    )

    engine = DecisionEngine()
    decision = engine.evaluate(analysis_job)

    assert decision.decision == "APPROVAL_REQUIRED"
    assert decision.safety_rule_triggered == "RULE_HIGH_STAKES_APPROVAL"


def test_groq_email_analyzer_mocked():
    """Verify EmailAnalyzer correctly calls Groq and parses JSON response."""
    mock_groq_response = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = """{
      "category": "Meeting Confirmation",
      "intent": "Confirming sync tomorrow",
      "main_topic": "Sync meeting",
      "urgency": "Medium",
      "importance": "Medium",
      "sentiment": "Positive",
      "is_sensitive": false,
      "is_suspicious_or_attack": false,
      "reply_required": true,
      "key_entities": ["Tomorrow 10 AM"],
      "summary": "Sender confirms sync.",
      "reasoning": "Routine calendar sync.",
      "confidence_score": 0.95
    }"""
    mock_groq_response.choices = [mock_choice]

    with patch("app.agent.email_analyzer.Groq") as mock_groq_class:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_groq_response
        mock_groq_class.return_value = mock_client

        analyzer = EmailAnalyzer(api_key="gsk_mock_test_key")
        result = analyzer.analyze("Alice", "alice@example.com", "Sync tomorrow", "Can we confirm?")

        assert result.category == "Meeting Confirmation"
        assert result.confidence_score == 0.95
        assert result.is_sensitive is False
