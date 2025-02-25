import email.utils
from collections.abc import AsyncGenerator
from datetime import datetime
from email.mime.text import MIMEText
from email.parser import BytesParser
from email.policy import default
from typing import Any

import aioimaplib
import aiosmtplib
from pydantic import BaseModel

from mcp_email_server.config import EmailServer, EmailSettings


class EmailData(BaseModel):
    subject: str
    sender: str
    body: str
    date: datetime
    attachments: list[str]

    @classmethod
    def from_email(cls, email: dict[str, Any]):
        return cls(
            subject=email["subject"],
            sender=email["from"],
            body=email["body"],
            date=email["date"],
            attachments=email["attachments"],
        )


class EmailPageResponse(BaseModel):
    page: int
    page_size: int
    before: datetime | None
    after: datetime | None
    include: str | None
    emails: list[EmailData]
    total: int


class EmailClient:
    def __init__(self, email_server: EmailServer, sender: str | None = None):
        self.email_server = email_server
        self.sender = sender or email_server.user_name

        self.imap_class = aioimaplib.IMAP4_SSL if self.email_server.use_ssl else aioimaplib.IMAP4

        self.smtp_use_tls = self.email_server.use_ssl
        self.smtp_start_tls = self.email_server.start_ssl

    def _parse_email_data(self, raw_email: bytes) -> dict[str, Any]:  # noqa: C901
        """Parse raw email data into a structured dictionary."""
        parser = BytesParser(policy=default)
        email_message = parser.parsebytes(raw_email)

        # Extract email parts
        subject = email_message.get("Subject", "")
        sender = email_message.get("From", "")
        date_str = email_message.get("Date", "")

        # Parse date
        try:
            date_tuple = email.utils.parsedate_tz(date_str)
            date = datetime.fromtimestamp(email.utils.mktime_tz(date_tuple)) if date_tuple else datetime.now()
        except Exception:
            date = datetime.now()

        # Get body content
        body = ""
        attachments = []

        if email_message.is_multipart():
            for part in email_message.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition", ""))

                # Handle attachments
                if "attachment" in content_disposition:
                    filename = part.get_filename()
                    if filename:
                        attachments.append(filename)
                # Handle text parts
                elif content_type == "text/plain":
                    body_part = part.get_payload(decode=True)
                    if body_part:
                        charset = part.get_content_charset("utf-8")
                        try:
                            body += body_part.decode(charset)
                        except UnicodeDecodeError:
                            body += body_part.decode("utf-8", errors="replace")
        else:
            # Handle plain text emails
            payload = email_message.get_payload(decode=True)
            if payload:
                charset = email_message.get_content_charset("utf-8")
                try:
                    body = payload.decode(charset)
                except UnicodeDecodeError:
                    body = payload.decode("utf-8", errors="replace")

        return {
            "subject": subject,
            "from": sender,
            "body": body,
            "date": date,
            "attachments": attachments,
        }

    async def get_emails_stream(  # noqa: C901
        self,
        page: int = 1,
        page_size: int = 10,
        before: datetime | None = None,
        after: datetime | None = None,
        include: str | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        imap = self.imap_class(self.email_server.host, self.email_server.port)
        try:
            # Wait for the connection to be established
            await imap._client_task
            await imap.wait_hello_from_server()

            # Login and select inbox
            await imap.login(self.email_server.user_name, self.email_server.password)
            await imap.select("INBOX")

            # Build search criteria
            search_criteria = "ALL"
            if before:
                search_criteria = f'(BEFORE "{before.isoformat()}")'
            if after:
                search_criteria = f'{search_criteria} (AFTER "{after.isoformat()}")'
            if include:
                search_criteria = f'{search_criteria} (TEXT "{include}")'

            # Search for messages
            _, messages = await imap.search(search_criteria)
            message_ids = messages[0].split()
            start = (page - 1) * page_size
            end = start + page_size

            # Fetch each message
            for _, message_id in enumerate(message_ids[start:end]):
                try:
                    # Convert message_id from bytes to string
                    message_id_str = message_id.decode("utf-8")

                    # Use the string version of the message ID
                    _, data = await imap.fetch(message_id_str, "RFC822")

                    # Find the email data in the response
                    raw_email = None

                    # The actual email content is in the bytearray at index 1
                    if len(data) > 1 and isinstance(data[1], bytearray) and len(data[1]) > 0:
                        raw_email = bytes(data[1])
                    else:
                        # Fallback to searching through all items
                        for _, item in enumerate(data):
                            if isinstance(item, (bytes, bytearray)) and len(item) > 100:
                                # Skip header lines that contain FETCH
                                if isinstance(item, bytes) and b"FETCH" in item:
                                    continue
                                # This is likely the email content
                                raw_email = bytes(item) if isinstance(item, bytearray) else item
                                break

                    if raw_email:
                        try:
                            parsed_email = self._parse_email_data(raw_email)
                            yield parsed_email
                        except Exception as e:
                            # Log error but continue with other emails
                            print(f"Error parsing email: {e!s}")
                    else:
                        print(f"Could not find email data in response for message ID: {message_id_str}")
                except Exception as e:
                    print(f"Error fetching message {message_id}: {e!s}")
        finally:
            # Ensure we logout properly
            try:
                await imap.logout()
            except Exception as e:
                print(f"Error during logout: {e}")

    async def get_email_count(
        self,
        before: datetime | None = None,
        after: datetime | None = None,
        include: str | None = None,
    ) -> int:
        imap = self.imap_class(self.email_server.host, self.email_server.port)
        try:
            # Wait for the connection to be established
            await imap._client_task
            await imap.wait_hello_from_server()

            # Login and select inbox
            await imap.login(self.email_server.user_name, self.email_server.password)
            await imap.select("INBOX")

            # Build search criteria
            search_criteria = "ALL"
            if before:
                search_criteria = f'(BEFORE "{before.isoformat()}")'
            if after:
                search_criteria = f'{search_criteria} (AFTER "{after.isoformat()}")'
            if include:
                search_criteria = f'{search_criteria} (TEXT "{include}")'

            # Search for messages and count them
            _, messages = await imap.search(search_criteria)
            return len(messages[0].split())
        finally:
            # Ensure we logout properly
            try:
                await imap.logout()
            except Exception as e:
                print(f"Error during logout: {e}")

    async def send_email(self, recipient: str, subject: str, body: str):
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = self.sender
        msg["To"] = recipient

        async with aiosmtplib.SMTP(
            hostname=self.email_server.host,
            port=self.email_server.port,
            start_tls=self.smtp_start_tls,
            use_tls=self.smtp_use_tls,
        ) as smtp:
            await smtp.login(self.email_server.user_name, self.email_server.password)
            await smtp.send_message(msg)


class ClassicEmailHandler:
    def __init__(self, email_settings: EmailSettings):
        self.email_settings = email_settings
        self.incoming_client = EmailClient(email_settings.incoming)
        self.outgoing_client = EmailClient(
            email_settings.outgoing,
            sender=f"{email_settings.full_name} <{email_settings.email_address}>",
        )

    async def get_emails(
        self,
        page: int = 1,
        page_size: int = 10,
        before: datetime | None = None,
        after: datetime | None = None,
        include: str | None = None,
    ) -> EmailPageResponse:
        emails = []
        async for email_data in self.incoming_client.get_emails_stream(page, page_size, before, after, include):
            emails.append(EmailData.from_email(email_data))
        total = await self.incoming_client.get_email_count(before, after, include)
        return EmailPageResponse(
            page=page,
            page_size=page_size,
            before=before,
            after=after,
            include=include,
            emails=emails,
            total=total,
        )

    async def send_email(self, recipient: str, subject: str, body: str):
        await self.outgoing_client.send_email(recipient, subject, body)
