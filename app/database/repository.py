"""Database Repository for Email and Audit Trail Operations."""

from datetime import datetime
from typing import List, Optional
from sqlalchemy.orm import Session
from app.database.models import ProcessedEmail, AgentLog, Contact


class EmailRepository:
    """Manages database access for incoming and outgoing email states."""

    def __init__(self, db: Session):
        self.db = db

    def email_exists(self, gmail_message_id: str) -> bool:
        """Check if an email has already been retrieved and processed."""
        return self.db.query(ProcessedEmail).filter(
            ProcessedEmail.gmail_message_id == gmail_message_id
        ).first() is not None

    def create_email_record(self, **kwargs) -> ProcessedEmail:
        """Create a new processed email record, gracefully handling race conditions."""
        msg_id = kwargs.get("gmail_message_id")
        if msg_id:
            existing = self.get_by_message_id(msg_id)
            if existing:
                for key, value in kwargs.items():
                    setattr(existing, key, value)
                try:
                    self.db.commit()
                    self.db.refresh(existing)
                    return existing
                except Exception:
                    self.db.rollback()
                    return existing

        record = ProcessedEmail(**kwargs)
        try:
            self.db.add(record)
            self.db.commit()
            self.db.refresh(record)
            return record
        except Exception:
            self.db.rollback()
            if msg_id:
                existing = self.get_by_message_id(msg_id)
                if existing:
                    return existing
            raise

    def update_email_record(self, email_id: int, **kwargs) -> Optional[ProcessedEmail]:
        """Update fields on an existing email record."""
        record = self.db.query(ProcessedEmail).filter(ProcessedEmail.id == email_id).first()
        if record:
            for key, value in kwargs.items():
                setattr(record, key, value)
            self.db.commit()
            self.db.refresh(record)
        return record

    def get_by_id(self, email_id: int) -> Optional[ProcessedEmail]:
        """Retrieve a specific record by its primary key ID."""
        return self.db.query(ProcessedEmail).filter(ProcessedEmail.id == email_id).first()

    def get_by_message_id(self, gmail_message_id: str) -> Optional[ProcessedEmail]:
        """Retrieve a record by its Gmail Message ID."""
        return self.db.query(ProcessedEmail).filter(
            ProcessedEmail.gmail_message_id == gmail_message_id
        ).first()

    def get_pending_approvals(self) -> List[ProcessedEmail]:
        """Retrieve all emails awaiting human review."""
        return self.db.query(ProcessedEmail).filter(
            ProcessedEmail.status == "pending_approval"
        ).order_by(ProcessedEmail.created_at.desc()).all()

    def get_auto_replied(self) -> List[ProcessedEmail]:
        """Retrieve all emails that were answered automatically."""
        return self.db.query(ProcessedEmail).filter(
            ProcessedEmail.status == "auto_replied"
        ).order_by(ProcessedEmail.sent_at.desc()).all()

    def get_all_emails(self, limit: int = 100) -> List[ProcessedEmail]:
        """Retrieve recent processed emails across all statuses."""
        return self.db.query(ProcessedEmail).order_by(
            ProcessedEmail.created_at.desc()
        ).limit(limit).all()

    def log_action(self, action: str, details: str, gmail_message_id: str = "", level: str = "INFO"):
        """Write an entry to the audit log."""
        log = AgentLog(
            action=action,
            details=details,
            gmail_message_id=gmail_message_id,
            level=level,
            timestamp=datetime.utcnow()
        )
        self.db.add(log)
        self.db.commit()

    def get_logs(self, limit: int = 100) -> List[AgentLog]:
        """Retrieve recent agent audit logs."""
        return self.db.query(AgentLog).order_by(AgentLog.timestamp.desc()).limit(limit).all()

    def get_statistics(self) -> dict:
        """Return real operational statistics computed from real database entries."""
        total = self.db.query(ProcessedEmail).count()
        auto_replied = self.db.query(ProcessedEmail).filter(ProcessedEmail.status == "auto_replied").count()
        pending = self.db.query(ProcessedEmail).filter(ProcessedEmail.status == "pending_approval").count()
        approved = self.db.query(ProcessedEmail).filter(ProcessedEmail.status == "approved_and_sent").count()
        ignored = self.db.query(ProcessedEmail).filter(ProcessedEmail.status.in_(["ignored", "quarantined", "rejected"])).count()

        return {
            "total_processed": total,
            "auto_replied": auto_replied,
            "pending_approval": pending,
            "approved_and_sent": approved,
            "ignored_or_quarantined": ignored
        }

    # ==================== CONTACTS / DIRECTORY ====================
    def add_contact(self, role_alias: str, full_name: str, email: str, department: str = "", notes: str = "") -> Contact:
        """Add or update a contact with a role alias (e.g. HOD, Class Teacher)."""
        existing = self.db.query(Contact).filter(
            Contact.role_alias.ilike(role_alias.strip())
        ).first()

        if existing:
            existing.full_name = full_name
            existing.email = email
            existing.department = department
            existing.notes = notes
            self.db.commit()
            self.db.refresh(existing)
            return existing

        contact = Contact(
            role_alias=role_alias.strip(),
            full_name=full_name.strip(),
            email=email.strip(),
            department=department.strip(),
            notes=notes.strip()
        )
        self.db.add(contact)
        self.db.commit()
        self.db.refresh(contact)
        return contact

    def get_all_contacts(self) -> List[Contact]:
        """Retrieve all registered contacts."""
        return self.db.query(Contact).order_by(Contact.role_alias.asc()).all()

    def find_contact_by_role_or_name(self, query_str: str) -> Optional[Contact]:
        """Search contact by role alias (e.g., 'hod') or name."""
        q = f"%{query_str.strip()}%"
        return self.db.query(Contact).filter(
            (Contact.role_alias.ilike(q)) | (Contact.full_name.ilike(q))
        ).first()

    def delete_contact(self, contact_id: int) -> bool:
        """Delete a contact by ID."""
        contact = self.db.query(Contact).filter(Contact.id == contact_id).first()
        if contact:
            self.db.delete(contact)
            self.db.commit()
            return True
        return False
