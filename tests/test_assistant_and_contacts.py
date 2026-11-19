"""Unit tests for Contact Directory, Chat Assistant, Sender, and Heuristic Filter."""

import pytest
from unittest.mock import MagicMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.models import Base, Contact
from app.database.repository import EmailRepository
from app.agent.chat_assistant import ChatAssistant
from app.gmail.email_sender import EmailSender
from app.services.automation_service import AutomationService, is_automated_broadcast


@pytest.fixture
def in_memory_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_contact_repository_crud(in_memory_db):
    """Test creating, reading, searching, updating, and deleting contacts."""
    repo = EmailRepository(in_memory_db)

    # 1. Add contact
    c1 = repo.add_contact(
        role_alias="HOD",
        full_name="Dr. Ramesh",
        email="hod.cse@college.edu",
        department="Computer Science",
        notes="Head of Department"
    )
    assert c1.id is not None
    assert c1.role_alias == "HOD"
    assert c1.email == "hod.cse@college.edu"

    # 2. Add second contact
    c2 = repo.add_contact(
        role_alias="Class Teacher",
        full_name="Mrs. Priya",
        email="priya.cse@college.edu",
        department="Computer Science",
        notes="Class Advisor"
    )
    assert c2.id is not None

    # 3. Retrieve all
    all_c = repo.get_all_contacts()
    assert len(all_c) == 2

    # 4. Search by role alias case-insensitively
    found = repo.find_contact_by_role_or_name("hod")
    assert found is not None
    assert found.full_name == "Dr. Ramesh"

    # 5. Search by partial name
    found_name = repo.find_contact_by_role_or_name("Priya")
    assert found_name is not None
    assert found_name.role_alias == "Class Teacher"

    # 6. Update existing contact via add_contact (upsert)
    updated = repo.add_contact(
        role_alias="HOD",
        full_name="Dr. Ramesh Kumar",
        email="new_hod@college.edu",
        department="CSE"
    )
    assert updated.id == c1.id
    assert updated.email == "new_hod@college.edu"

    # 7. Delete contact
    deleted = repo.delete_contact(c2.id)
    assert deleted is True
    assert len(repo.get_all_contacts()) == 1


def test_chat_assistant_contacts_context(in_memory_db):
    """Verify that ChatAssistant injects all saved contacts into its context prompt."""
    repo = EmailRepository(in_memory_db)
    repo.add_contact("HOD", "Dr. Ramesh", "hod@college.edu", "CSE")
    repo.add_contact("Class Teacher", "Mrs. Priya", "priya@college.edu", "CSE")

    assistant = ChatAssistant(in_memory_db)
    context_str = assistant._build_contacts_context()

    assert "Role/Alias: 'HOD'" in context_str
    assert "hod@college.edu" in context_str
    assert "Role/Alias: 'Class Teacher'" in context_str
    assert "priya@college.edu" in context_str


def test_chat_assistant_draft_email_mocked(in_memory_db):
    """Test ChatAssistant with a simulated Groq JSON response."""
    repo = EmailRepository(in_memory_db)
    repo.add_contact("HOD", "Dr. Ramesh", "hod@college.edu", "CSE")
    repo.add_contact("Class Teacher", "Mrs. Priya", "priya@college.edu", "CSE")

    assistant = ChatAssistant(in_memory_db)

    mock_json_reply = """{
        "action": "SEND_EMAIL",
        "reply_message": "Drafted leave request for HOD and CC'd Class Teacher.",
        "email_draft": {
            "recipient_name": "Dr. Ramesh",
            "recipient_email": "hod@college.edu",
            "cc_emails": "priya@college.edu",
            "subject": "Leave Request for Medical Reasons",
            "body": "Dear Dr. Ramesh,\\n\\nPlease grant me 2 days leave due to fever.\\n\\nBest regards,\\nSanthosh"
        }
    }"""

    mock_completion = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = mock_json_reply
    mock_completion.choices = [mock_choice]

    assistant.client = MagicMock()
    assistant.client.chat.completions.create.return_value = mock_completion

    result = assistant.chat("Send mail to HOD asking for leave for 2 days due to fever, attach class teacher")

    assert result["action"] == "SEND_EMAIL"
    assert result["email_draft"]["recipient_email"] == "hod@college.edu"
    assert result["email_draft"]["cc_emails"] == "priya@college.edu"
    assert "Leave Request" in result["email_draft"]["subject"]


def test_email_sender_send_new_email():
    """Verify EmailSender properly constructs and sends a new MIME email with CC."""
    mock_service = MagicMock()
    mock_messages = MagicMock()
    mock_send = MagicMock()
    mock_send.execute.return_value = {"id": "sent_12345"}
    mock_messages.send.return_value = mock_send
    mock_service.users.return_value.messages.return_value = mock_messages

    sender = EmailSender(mock_service)
    sent_id = sender.send_new_email(
        to_email="hod@college.edu",
        subject="Leave Application",
        body="Dear Sir, I am unwell.",
        cc_emails="classteacher@college.edu"
    )

    assert sent_id == "sent_12345"
    mock_messages.send.assert_called_once()
    args, kwargs = mock_messages.send.call_args
    assert kwargs["userId"] == "me"
    assert "raw" in kwargs["body"]


def test_heuristic_broadcast_filter():
    """Verify that automated system alerts bypass Groq API to save calls."""
    # 1. No-reply email should be detected as broadcast
    assert is_automated_broadcast(
        sender_email="no-reply@classroom.google.com",
        sender_name="Google Classroom",
        subject="New announcement: Lecture notes"
    ) is True

    # 2. LinkedIn security notification
    assert is_automated_broadcast(
        sender_email="notifications-noreply@linkedin.com",
        sender_name="LinkedIn",
        subject="You have 3 new notifications"
    ) is True

    # 3. Real personal or human email should NOT be filtered
    assert is_automated_broadcast(
        sender_email="colleague@company.com",
        sender_name="Alex Turner",
        subject="Project meeting agenda tomorrow"
    ) is False
