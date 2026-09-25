from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class NotificationMessage:
    """Standard message structure passed to notification backends."""
    ps_id: str
    ps_title: str
    previous_count: Optional[int]
    current_count: int
    increase: int
    detected_at: str
    portal_url: str = "https://sih.gov.in/sih2026PS"
    source: str = "SIH Portal"

    @property
    def plain_text(self) -> str:
        prev_str = str(self.previous_count) if self.previous_count is not None else "N/A"
        inc_str = f"+{self.increase}" if self.increase > 0 else str(self.increase)
        return (
            f"SIH Problem Statement Count Increased\n\n"
            f"Problem Statement:\n"
            f"{self.ps_id} - {self.ps_title}\n\n"
            f"Previous Count: {prev_str}\n"
            f"New Count: {self.current_count}\n"
            f"Increase: {inc_str}\n\n"
            f"Detected At:\n"
            f"{self.detected_at}\n\n"
            f"Source:\n"
            f"{self.source}"
        )


class NotificationService(ABC):
    """Abstract base class for all notification services."""

    @abstractmethod
    def send(self, message: NotificationMessage) -> bool:
        """
        Send notification.
        Returns True if sent successfully, False otherwise.
        Must NOT raise unhandled exceptions that crash the caller.
        """
        raise NotImplementedError

    @abstractmethod
    def test_connection(self) -> bool:
        """
        Test the notification service configuration and connectivity.
        """
        raise NotImplementedError
