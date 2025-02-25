from mcp_email_server.config import EmailServer, EmailSettings


class EmailClient:
    def __init__(self, email_server: EmailServer):
        self.email_server = email_server


class ClassicEmailHandler:
    def __init__(self, email_settings: EmailSettings):
        self.email_settings = email_settings
        self.incoming_client = EmailClient(email_settings.incoming)
        self.outgoing_client = EmailClient(email_settings.outgoing)
