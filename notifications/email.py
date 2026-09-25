import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, List, Union

from .base import NotificationService, NotificationMessage

logger = logging.getLogger("sih_monitor.notifications.email")


class EmailNotification(NotificationService):
    """
    SMTP Email notification backend supporting Gmail SMTP and custom SMTP relays.
    Supports single or multiple recipients (as a list or comma-separated string).
    """

    def __init__(
        self,
        smtp_host: str = "smtp.gmail.com",
        smtp_port: int = 587,
        sender: str = "",
        recipient: Union[str, List[str]] = "",
        app_password: str = "",
        use_tls: bool = True
    ):
        self.smtp_host = smtp_host
        self.smtp_port = int(smtp_port)
        self.sender = sender.strip()
        self.recipients = self._parse_recipients(recipient)
        self.recipient = ", ".join(self.recipients)  # Backward compatibility string
        self.app_password = app_password.strip()
        self.use_tls = use_tls

    @staticmethod
    def _parse_recipients(recipient_input: Union[str, List[str]]) -> List[str]:
        """Normalize recipient string or list into a clean list of email addresses."""
        if not recipient_input:
            return []
        if isinstance(recipient_input, list):
            items = []
            for item in recipient_input:
                if isinstance(item, str):
                    items.extend([e.strip() for e in item.replace(";", ",").split(",") if e.strip()])
            return items
        elif isinstance(recipient_input, str):
            return [e.strip() for e in recipient_input.replace(";", ",").split(",") if e.strip()]
        return []

    def _is_configured(self) -> bool:
        return bool(self.sender and self.recipients and self.app_password and "dummy" not in self.app_password.lower())


    def _build_html_body(self, msg: NotificationMessage) -> str:
        prev_str = str(msg.previous_count) if msg.previous_count is not None else "Baseline"
        inc_str = f"+{msg.increase}" if msg.increase > 0 else str(msg.increase)
        
        return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>SIH PS Count Increased</title>
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f4f6f8; margin: 0; padding: 20px;">
  <div style="max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.08); border: 1px solid #e1e4e8;">
    <div style="background: linear-gradient(135deg, #1e3a8a 0%, #3b82f6 100%); color: #ffffff; padding: 24px; text-align: center;">
      <h1 style="margin: 0; font-size: 22px; font-weight: 700; letter-spacing: 0.5px;">🚨 SIH PS Count Increased</h1>
      <p style="margin: 6px 0 0 0; opacity: 0.9; font-size: 14px;">Smart India Hackathon Real-Time Alert</p>
    </div>
    
    <div style="padding: 24px;">
      <div style="background: #f8fafc; border-left: 4px solid #3b82f6; padding: 14px 16px; margin-bottom: 20px; border-radius: 4px;">
        <div style="font-size: 12px; font-weight: 600; text-transform: uppercase; color: #64748b; margin-bottom: 4px;">Problem Statement</div>
        <div style="font-size: 18px; font-weight: bold; color: #0f172a;">{msg.ps_id}</div>
        <div style="font-size: 15px; color: #334155; margin-top: 4px; line-height: 1.4;">{msg.ps_title}</div>
      </div>

      <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px;">
        <tr>
          <td style="padding: 12px; background: #f1f5f9; border-radius: 6px; text-align: center; width: 33%;">
            <div style="font-size: 12px; color: #64748b; text-transform: uppercase; font-weight: 600;">Previous</div>
            <div style="font-size: 22px; font-weight: 700; color: #475569; margin-top: 4px;">{prev_str}</div>
          </td>
          <td style="width: 5%;"></td>
          <td style="padding: 12px; background: #dbeafe; border-radius: 6px; text-align: center; width: 33%;">
            <div style="font-size: 12px; color: #1e40af; text-transform: uppercase; font-weight: 600;">New Count</div>
            <div style="font-size: 22px; font-weight: 700; color: #1e3a8a; margin-top: 4px;">{msg.current_count}</div>
          </td>
          <td style="width: 5%;"></td>
          <td style="padding: 12px; background: #dcfce7; border-radius: 6px; text-align: center; width: 33%;">
            <div style="font-size: 12px; color: #166534; text-transform: uppercase; font-weight: 600;">Increase</div>
            <div style="font-size: 22px; font-weight: 700; color: #15803d; margin-top: 4px;">{inc_str}</div>
          </td>
        </tr>
      </table>

      <div style="font-size: 13px; color: #64748b; line-height: 1.6; border-top: 1px solid #e2e8f0; padding-top: 16px;">
        <div><strong>🕒 Detected At:</strong> {msg.detected_at}</div>
        <div><strong>🌐 Source:</strong> <a href="{msg.portal_url}" style="color: #2563eb; text-decoration: none;">{msg.source}</a></div>
      </div>

      <div style="margin-top: 24px; text-align: center;">
        <a href="{msg.portal_url}" style="display: inline-block; background: #2563eb; color: #ffffff; padding: 10px 20px; border-radius: 6px; font-weight: 600; font-size: 14px; text-decoration: none;">View on SIH Portal</a>
      </div>
    </div>

    <div style="background: #f8fafc; padding: 12px 24px; text-align: center; font-size: 12px; color: #94a3b8; border-top: 1px solid #e2e8f0;">
      Automated alert generated by SIH Problem Statement Monitor
    </div>
  </div>
</body>
</html>"""

    def send(self, message: NotificationMessage) -> bool:
        if not self._is_configured():
            logger.warning("Email notification skipped: SMTP credentials not fully configured.")
            return False

        subject = f"SIH PS Count Increased: {message.ps_id} (+{message.increase})"
        
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.sender
        msg["To"] = ", ".join(self.recipients)

        # Attach text and html versions
        part_text = MIMEText(message.plain_text, "plain", "utf-8")
        part_html = MIMEText(self._build_html_body(message), "html", "utf-8")
        msg.attach(part_text)
        msg.attach(part_html)

        try:
            logger.info("Connecting to SMTP server %s:%d to send alert for %s to %d recipient(s)", 
                        self.smtp_host, self.smtp_port, message.ps_id, len(self.recipients))
            server = smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=20)
            if self.use_tls:
                server.starttls()
            server.login(self.sender, self.app_password)
            server.sendmail(self.sender, self.recipients, msg.as_string())
            server.quit()
            logger.info("Email notification successfully sent to %s for %s", ", ".join(self.recipients), message.ps_id)
            return True
        except Exception as e:
            logger.error("Failed to send email notification: %s", e)
            return False


    def test_connection(self) -> bool:
        if not self._is_configured():
            logger.error("Email test failed: Missing SMTP credentials in .env or config.yaml")
            return False

        try:
            logger.info("Testing SMTP connection to %s:%d...", self.smtp_host, self.smtp_port)
            server = smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=15)
            if self.use_tls:
                server.starttls()
            server.login(self.sender, self.app_password)
            server.quit()
            logger.info("SMTP test connection successful!")
            return True
        except Exception as e:
            logger.error("SMTP test connection failed: %s", e)
            return False
