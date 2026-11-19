"""AI Automatic Email Reply Agent - Main CLI Controller.

Provides convenient commands to authenticate, synchronize, and run the real-time monitor.
"""

import argparse
import sys
from pathlib import Path

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.config.settings import settings
from app.database.connection import init_db, SessionLocal
from app.database.repository import EmailRepository
from app.gmail.authentication import GmailAuthenticator
from app.gmail.email_monitor import EmailMonitor
from app.services.automation_service import AutomationService


def print_banner():
    print("=" * 70)
    print("   AI AUTOMATIC EMAIL REPLY AGENT (GROQ POWERED)")
    print("=" * 70)
    print(f" Provider: Groq ({settings.GROQ_MODEL})")
    print(f" Owner:    {settings.USER_NAME} ({settings.USER_ROLE})")
    print(f" Auto-Reply Mode: {'ENABLED (Will send safe replies automatically)' if settings.AUTO_REPLY_ENABLED else 'DISABLED (Queuing for review)'}")
    print("=" * 70)


def cmd_auth():
    print("\n[*] Initializing Gmail OAuth 2.0 Authentication...")
    auth = GmailAuthenticator()
    try:
        auth.authenticate_interactive()
        print("[SUCCESS] Connected to Gmail! Token saved to", settings.GMAIL_TOKEN_FILE)
    except Exception as e:
        print(f"[ERROR] Authentication failed: {e}")
        print("\nMake sure you have placed your 'credentials.json' from Google Cloud Console into the project folder.")


def cmd_sync():
    print("\n[*] Synchronizing inbox with Gmail & Groq...")
    init_db()
    db = SessionLocal()
    try:
        service = AutomationService(db)
        result = service.process_incoming_emails()
        print("\nSync Results:")
        print(f" • Total Fetched:     {result.get('total_fetched', 0)}")
        print(f" • Auto-Replied:      {result.get('auto_replied', 0)}")
        print(f" • Pending Review:    {result.get('pending_approval', 0)}")
        print(f" • Suppressed/Ignored:{result.get('do_not_reply', 0)}")
        if result.get("message"):
            print(f" • Message: {result.get('message')}")
    finally:
        db.close()


def cmd_monitor():
    print_banner()
    init_db()
    monitor = EmailMonitor()
    monitor.start_loop()


def cmd_stats():
    init_db()
    db = SessionLocal()
    try:
        repo = EmailRepository(db)
        stats = repo.get_statistics()
        print("\n=== Live Real Database Statistics ===")
        print(f"Total Emails Processed:  {stats['total_processed']}")
        print(f"Automatically Replied:   {stats['auto_replied']}")
        print(f"Pending User Approval:   {stats['pending_approval']}")
        print(f"Manually Approved & Sent:{stats['approved_and_sent']}")
        print(f"Ignored or Quarantined:  {stats['ignored_or_quarantined']}")
        print("=====================================")
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="AI Automatic Email Reply Agent CLI")
    parser.add_argument("--auth", action="store_true", help="Connect your Gmail account via Google OAuth 2.0")
    parser.add_argument("--sync", action="store_true", help="Perform a single fetch-and-auto-reply synchronization cycle")
    parser.add_argument("--monitor", action="store_true", help="Start continuous real-time email monitor loop")
    parser.add_argument("--stats", action="store_true", help="Display live database email statistics")
    parser.add_argument("--init-db", action="store_true", help="Initialize the SQLite database schema")

    args = parser.parse_args()

    if args.auth:
        cmd_auth()
    elif args.sync:
        cmd_sync()
    elif args.monitor:
        cmd_monitor()
    elif args.stats:
        cmd_stats()
    elif args.init_db:
        init_db()
        print("[SUCCESS] Database tables initialized at:", settings.DATABASE_URL)
    else:
        print_banner()
        parser.print_help()


if __name__ == "__main__":
    main()
