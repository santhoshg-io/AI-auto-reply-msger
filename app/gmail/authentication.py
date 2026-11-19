"""Gmail OAuth 2.0 Authentication Service.

Manages user consent, local token persistence (token.json), and automatic token refreshes.
Never stores or requests plain passwords.
"""

import logging
import os
from typing import Optional
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build, Resource

from app.config.settings import settings

logger = logging.getLogger(__name__)

# Scopes required: reading emails, sending responses, and modifying labels (mark as read)
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify"
]


class GmailAuthenticator:
    """Handles Google OAuth2 authentication flow and token refresh lifecycle."""

    def __init__(self, credentials_file: str = None, token_file: str = None):
        self.credentials_file = credentials_file or settings.GMAIL_CREDENTIALS_FILE
        self.token_file = token_file or settings.GMAIL_TOKEN_FILE
        self.creds: Optional[Credentials] = None

    def get_credentials(self) -> Optional[Credentials]:
        """Load valid credentials from token file or return None if user needs to authenticate."""
        creds = None

        if os.path.exists(self.token_file):
            try:
                creds = Credentials.from_authorized_user_file(self.token_file, SCOPES)
            except Exception as e:
                logger.error("Error reading token file: %s", e)
                creds = None

        # Refresh if expired
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                with open(self.token_file, "w", encoding="utf-8") as token_out:
                    token_out.write(creds.to_json())
                logger.info("Gmail OAuth token refreshed successfully.")
            except Exception as e:
                logger.warning("Could not refresh token: %s", e)
                creds = None

        self.creds = creds
        return creds

    def authenticate_interactive(self) -> Credentials:
        """Run interactive browser-based OAuth flow to obtain token.json."""
        if not os.path.exists(self.credentials_file):
            raise FileNotFoundError(
                f"Google OAuth credentials file '{self.credentials_file}' not found. "
                "Download your OAuth client credentials JSON from Google Cloud Console "
                f"and place it at '{self.credentials_file}'."
            )

        flow = InstalledAppFlow.from_client_secrets_file(self.credentials_file, SCOPES)
        creds = flow.run_local_server(port=0)

        # Save credentials for future executions
        with open(self.token_file, "w", encoding="utf-8") as token_out:
            token_out.write(creds.to_json())

        self.creds = creds
        logger.info("OAuth2 authentication successful. Token saved to %s", self.token_file)
        return creds

    def is_connected(self) -> bool:
        """Check if active valid credentials exist."""
        creds = self.get_credentials()
        return creds is not None and creds.valid

    def get_service(self) -> Resource:
        """Build and return an authorized Gmail API service client."""
        creds = self.get_credentials()
        if not creds or not creds.valid:
            creds = self.authenticate_interactive()

        return build("gmail", "v1", credentials=creds)
