"""Background Email Monitoring Service.

Continuously polls Gmail for newly received messages and triggers the AI agent pipeline.
"""

import logging
import time
from app.config.settings import settings
from app.database.connection import SessionLocal
from app.services.automation_service import AutomationService

logger = logging.getLogger(__name__)


class EmailMonitor:
    """Monitors Gmail inbox on a periodic schedule."""

    def __init__(self, poll_interval: int = None):
        self.poll_interval = poll_interval or settings.POLL_INTERVAL_SECONDS
        self._running = False

    def run_once(self) -> dict:
        """Execute a single synchronization cycle."""
        db = SessionLocal()
        try:
            service = AutomationService(db)
            return service.process_incoming_emails()
        finally:
            db.close()

    def start_loop(self):
        """Start the continuous background polling loop."""
        self._running = True
        logger.info("Starting Email Monitor loop (Polling every %d seconds)...", self.poll_interval)
        print(f"[*] AI Email Agent monitor started. Checking inbox every {self.poll_interval}s. Press Ctrl+C to stop.")

        while self._running:
            try:
                result = self.run_once()
                if result.get("auto_replied", 0) > 0 or result.get("pending_approval", 0) > 0:
                    print(f"[+] Sync Cycle: Auto-Replied: {result.get('auto_replied')}, Pending Review: {result.get('pending_approval')}")
            except Exception as e:
                logger.error("Error during monitor cycle: %s", e)
                print(f"[!] Monitor error: {e}")

            try:
                time.sleep(self.poll_interval)
            except KeyboardInterrupt:
                print("\n[*] Stopping Email Monitor...")
                self._running = False
                break

    def stop(self):
        """Stop the loop."""
        self._running = False
