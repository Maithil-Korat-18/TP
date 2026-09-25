import logging
from typing import Optional

from .base import NotificationService, NotificationMessage

logger = logging.getLogger("sih_monitor.notifications.whatsapp")


class WhatsAppNotification(NotificationService):
    """
    Twilio WhatsApp notification backend.
    """

    def __init__(
        self,
        account_sid: str = "",
        auth_token: str = "",
        from_number: str = "",
        to_number: str = ""
    ):
        self.account_sid = account_sid.strip()
        self.auth_token = auth_token.strip()
        self.from_number = from_number.strip()
        self.to_number = to_number.strip()

    def _is_configured(self) -> bool:
        return bool(
            self.account_sid
            and self.auth_token
            and self.from_number
            and self.to_number
            and "dummy" not in self.account_sid.lower()
        )

    def _format_whatsapp_body(self, msg: NotificationMessage) -> str:
        prev_str = str(msg.previous_count) if msg.previous_count is not None else "Baseline"
        inc_str = f"+{msg.increase}" if msg.increase > 0 else str(msg.increase)
        
        return (
            f"🚨 *SIH PS COUNT INCREASED*\n\n"
            f"*PS:* {msg.ps_id}\n"
            f"_{msg.ps_title}_\n\n"
            f"*Previous:* {prev_str}\n"
            f"*Current:* {msg.current_count}\n"
            f"*Increase:* {inc_str}\n\n"
            f"*Time:* {msg.detected_at}\n"
            f"*Portal:* {msg.portal_url}"
        )

    def send(self, message: NotificationMessage) -> bool:
        if not self._is_configured():
            logger.warning("WhatsApp notification skipped: Twilio credentials not configured.")
            return False

        try:
            from twilio.rest import Client
        except ImportError:
            logger.error("Twilio package not installed. Run: pip install twilio")
            return False

        body = self._format_whatsapp_body(message)
        
        # Ensure 'whatsapp:' prefix
        from_formatted = self.from_number if self.from_number.startswith("whatsapp:") else f"whatsapp:{self.from_number}"
        to_formatted = self.to_number if self.to_number.startswith("whatsapp:") else f"whatsapp:{self.to_number}"

        try:
            client = Client(self.account_sid, self.auth_token)
            message_obj = client.messages.create(
                body=body,
                from_=from_formatted,
                to=to_formatted
            )
            logger.info("WhatsApp notification sent via Twilio (SID: %s) for %s", message_obj.sid, message.ps_id)
            return True
        except Exception as e:
            logger.error("Failed to send WhatsApp notification via Twilio: %s", e)
            return False

    def test_connection(self) -> bool:
        if not self._is_configured():
            logger.error("WhatsApp test failed: Twilio credentials not configured in .env or config.yaml")
            return False

        try:
            from twilio.rest import Client
            client = Client(self.account_sid, self.auth_token)
            account = client.api.accounts(self.account_sid).fetch()
            logger.info("Twilio WhatsApp connection test successful! Account: %s (Status: %s)", account.friendly_name, account.status)
            return True
        except Exception as e:
            logger.error("Twilio test connection failed: %s", e)
            return False
