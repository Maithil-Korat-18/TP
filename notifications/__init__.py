"""Notification services package for SIH PS Monitor."""
from typing import List, Dict, Any

from .base import NotificationService, NotificationMessage
from .email import EmailNotification
from .whatsapp import WhatsAppNotification


class NotificationDispatcher:
    """Dispatches alerts to all enabled notification services."""

    def __init__(self, services: List[NotificationService]):
        self.services = services

    def broadcast(self, message: NotificationMessage) -> Dict[str, bool]:
        """Broadcast alert to all registered services without failing on one."""
        results = {}
        for idx, service in enumerate(self.services):
            name = getattr(service, "name", service.__class__.__name__)
            key = name if name not in results else f"{name}_{idx}"
            try:
                success = service.send(message)
                results[key] = bool(success)
            except Exception:
                results[key] = False
        return results



def build_notification_dispatcher(config: dict) -> NotificationDispatcher:
    """Build dispatcher from notification config."""
    services: List[NotificationService] = []
    notif_cfg = config.get("notification", {})

    # Email
    email_cfg = notif_cfg.get("email", {})
    if email_cfg.get("enabled", False):
        recipients = email_cfg.get("recipients") or email_cfg.get("recipient", "")
        services.append(
            EmailNotification(
                smtp_host=email_cfg.get("smtp_host", "smtp.gmail.com"),
                smtp_port=email_cfg.get("smtp_port", 587),
                sender=email_cfg.get("sender", ""),
                recipient=recipients,
                app_password=email_cfg.get("app_password", ""),
                use_tls=email_cfg.get("use_tls", True),
            )
        )


    # WhatsApp
    wa_cfg = notif_cfg.get("whatsapp", {})
    if wa_cfg.get("enabled", False):
        services.append(
            WhatsAppNotification(
                account_sid=wa_cfg.get("account_sid", ""),
                auth_token=wa_cfg.get("auth_token", ""),
                from_number=wa_cfg.get("from_number", ""),
                to_number=wa_cfg.get("to_number", ""),
            )
        )

    return NotificationDispatcher(services)


__all__ = [
    "NotificationService",
    "NotificationMessage",
    "EmailNotification",
    "WhatsAppNotification",
    "NotificationDispatcher",
    "build_notification_dispatcher",
]
