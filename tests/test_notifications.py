from unittest.mock import patch, MagicMock
import pytest

from notifications.base import NotificationMessage, NotificationService
from notifications.email import EmailNotification
from notifications.whatsapp import WhatsAppNotification
from notifications import NotificationDispatcher


@pytest.fixture
def sample_message():
    return NotificationMessage(
        ps_id="SIH1234",
        ps_title="Crop Disease Detection",
        previous_count=37,
        current_count=42,
        increase=5,
        detected_at="25 Sep 2026, 11:30 AM",
        portal_url="https://sih.gov.in/sih2026PS",
        source="SIH Portal"
    )


def test_plain_text_message(sample_message):
    text = sample_message.plain_text
    assert "SIH1234 - Crop Disease Detection" in text
    assert "Previous Count: 37" in text
    assert "New Count: 42" in text
    assert "Increase: +5" in text
    assert "25 Sep 2026, 11:30 AM" in text


def test_email_unconfigured(sample_message):
    email_service = EmailNotification(sender="", recipient="", app_password="")
    # Should not raise exception, return False gracefully
    assert not email_service.send(sample_message)
    assert not email_service.test_connection()


@patch("smtplib.SMTP")
def test_email_send_success(mock_smtp, sample_message):
    mock_instance = MagicMock()
    mock_smtp.return_value = mock_instance

    email_service = EmailNotification(
        smtp_host="smtp.gmail.com",
        smtp_port=587,
        sender="sender@gmail.com",
        recipient="recipient@gmail.com",
        app_password="real_app_password"
    )

    success = email_service.send(sample_message)
    assert success is True
    assert mock_instance.starttls.called
    assert mock_instance.login.called
    assert mock_instance.sendmail.called
    args, kwargs = mock_instance.sendmail.call_args
    assert args[1] == ["recipient@gmail.com"]


@patch("smtplib.SMTP")
def test_email_send_multiple_recipients_list_and_string(mock_smtp, sample_message):
    mock_instance = MagicMock()
    mock_smtp.return_value = mock_instance

    # Test comma-separated string
    email_service_str = EmailNotification(
        sender="sender@gmail.com",
        recipient="alice@gmail.com, bob@gmail.com; charlie@gmail.com",
        app_password="real_app_password"
    )
    assert email_service_str.recipients == ["alice@gmail.com", "bob@gmail.com", "charlie@gmail.com"]
    email_service_str.send(sample_message)
    args, _ = mock_instance.sendmail.call_args
    assert args[1] == ["alice@gmail.com", "bob@gmail.com", "charlie@gmail.com"]

    # Test list
    email_service_list = EmailNotification(
        sender="sender@gmail.com",
        recipient=["alice@gmail.com", "bob@gmail.com"],
        app_password="real_app_password"
    )
    assert email_service_list.recipients == ["alice@gmail.com", "bob@gmail.com"]
    email_service_list.send(sample_message)
    args, _ = mock_instance.sendmail.call_args
    assert args[1] == ["alice@gmail.com", "bob@gmail.com"]



@patch("smtplib.SMTP")
def test_email_send_failure_handled(mock_smtp, sample_message):
    mock_smtp.side_effect = Exception("SMTP Server Down")

    email_service = EmailNotification(
        smtp_host="smtp.gmail.com",
        smtp_port=587,
        sender="sender@gmail.com",
        recipient="recipient@gmail.com",
        app_password="real_app_password"
    )

    # Must NOT raise exception to prevent crashing the monitor
    success = email_service.send(sample_message)
    assert success is False


def test_whatsapp_unconfigured(sample_message):
    wa_service = WhatsAppNotification(account_sid="", auth_token="", from_number="", to_number="")
    assert not wa_service.send(sample_message)
    assert not wa_service.test_connection()


@patch("twilio.rest.Client")
def test_whatsapp_send_success(mock_twilio, sample_message):
    mock_client = MagicMock()
    mock_twilio.return_value = mock_client

    wa_service = WhatsAppNotification(
        account_sid="AC1234567890abcdef",
        auth_token="token123456",
        from_number="whatsapp:+14155238886",
        to_number="whatsapp:+919876543210"
    )

    success = wa_service.send(sample_message)
    assert success is True
    assert mock_client.messages.create.called


@patch("twilio.rest.Client")
def test_whatsapp_send_failure_handled(mock_twilio, sample_message):
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = Exception("Twilio API Error")
    mock_twilio.return_value = mock_client

    wa_service = WhatsAppNotification(
        account_sid="AC1234567890abcdef",
        auth_token="token123456",
        from_number="whatsapp:+14155238886",
        to_number="whatsapp:+919876543210"
    )

    # Must NOT crash
    success = wa_service.send(sample_message)
    assert success is False


def test_dispatcher_handles_mixed_results(sample_message):
    service_good = MagicMock(spec=NotificationService)
    service_good.send.return_value = True

    service_failing = MagicMock(spec=NotificationService)
    service_failing.send.side_effect = RuntimeError("Fatal Notification Provider Crash")

    dispatcher = NotificationDispatcher([service_good, service_failing])
    results = dispatcher.broadcast(sample_message)

    assert len(results) == 2
    assert any(v is True for v in results.values())
    assert any(v is False for v in results.values())
