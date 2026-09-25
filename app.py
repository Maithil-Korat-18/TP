#!/usr/bin/env python3
"""
Smart India Hackathon (SIH) Problem Statement Count Monitor.

Production-ready monitoring system with automated email & WhatsApp alerts,
historical tracking, retry backoff, and duplicate alert prevention.
"""

import os
import sys
import re
import json
import logging
import argparse
import datetime
from logging.handlers import RotatingFileHandler
from typing import Dict, Any

import yaml
from dotenv import load_dotenv
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

# Ensure local packages can be imported
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


from database import DatabaseManager
from scraper import get_scraper
from notifications import (
    build_notification_dispatcher,
    NotificationMessage,
    EmailNotification,
    WhatsAppNotification,
)
from monitor import SihMonitor


def setup_logging(log_dir: str = "logs", log_level: int = logging.INFO) -> None:
    """Configure console and rotating file logging."""
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "sih_monitor.log")

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(log_level)

    # Rotating file handler (5 MB max, up to 5 backups)
    file_handler = RotatingFileHandler(
        log_file, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(log_level)

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    # Avoid duplicate handlers if reconfigured
    root_logger.handlers = []
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)


def expand_env_vars(data: Any) -> Any:
    """Recursively expand ${VAR} or $VAR environment variables in config values."""
    if isinstance(data, dict):
        return {k: expand_env_vars(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [expand_env_vars(v) for v in data]
    elif isinstance(data, str):
        # Match ${VAR_NAME} or ${VAR_NAME:default}
        pattern = re.compile(r"\$\{([A-Za-z0-9_]+)(?::([^}]*))?\}")
        def replace(match):
            var_name = match.group(1)
            default_val = match.group(2) if match.group(2) is not None else ""
            return os.getenv(var_name, default_val)
        return pattern.sub(replace, data)
    return data


def load_configuration(config_path: str = "config.yaml") -> Dict[str, Any]:
    """Load .env secrets and YAML configuration file."""
    load_dotenv(override=True)
    
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Configuration file not found at: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        raw_config = yaml.safe_load(f) or {}

    config = expand_env_vars(raw_config)

    # Fallback env mapping for convenience if not using ${VAR} syntax
    email_cfg = config.setdefault("notification", {}).setdefault("email", {})
    if not email_cfg.get("sender"):
        email_cfg["sender"] = os.getenv("SMTP_SENDER", "")
    if not email_cfg.get("recipient") and not email_cfg.get("recipients"):
        email_cfg["recipient"] = os.getenv("SMTP_RECIPIENT", os.getenv("SMTP_RECIPIENTS", ""))
    if not email_cfg.get("app_password"):
        email_cfg["app_password"] = os.getenv("SMTP_APP_PASSWORD", "")

    wa_cfg = config.setdefault("notification", {}).setdefault("whatsapp", {})
    if not wa_cfg.get("account_sid"):
        wa_cfg["account_sid"] = os.getenv("TWILIO_ACCOUNT_SID", "")
    if not wa_cfg.get("auth_token"):
        wa_cfg["auth_token"] = os.getenv("TWILIO_AUTH_TOKEN", "")
    if not wa_cfg.get("from_number"):
        wa_cfg["from_number"] = os.getenv("TWILIO_FROM_NUMBER", "")
    if not wa_cfg.get("to_number"):
        wa_cfg["to_number"] = os.getenv("TWILIO_TO_NUMBER", "")

    return config


def test_email(config: Dict[str, Any]) -> None:
    """Test SMTP email configuration."""
    print("\n--- Testing Email Notification ---")
    email_cfg = config.get("notification", {}).get("email", {})
    sender = email_cfg.get("sender", "")
    recipients = email_cfg.get("recipients") or email_cfg.get("recipient", "")
    host = email_cfg.get("smtp_host", "smtp.gmail.com")
    port = email_cfg.get("smtp_port", 587)

    print(f"SMTP Host: {host}:{port}")
    print(f"Sender: {sender}")
    print(f"Recipient(s): {recipients}")

    if not sender or not email_cfg.get("app_password"):
        print("ERROR: Email credentials are missing in .env or config.yaml")
        print("Please set SMTP_SENDER and SMTP_APP_PASSWORD in your .env file.")
        return


    service = EmailNotification(
        smtp_host=host,
        smtp_port=port,
        sender=sender,
        recipient=recipients,
        app_password=email_cfg.get("app_password", ""),
        use_tls=email_cfg.get("use_tls", True)
    )


    test_msg = NotificationMessage(
        ps_id="TEST-SIH",
        ps_title="Test Problem Statement Alert Verification",
        previous_count=10,
        current_count=15,
        increase=5,
        detected_at=datetime.datetime.now().strftime("%d %b %Y, %I:%M %p"),
        portal_url=config.get("sih", {}).get("url", "https://sih.gov.in/sih2026PS"),
        source="Test Execution"
    )

    success = service.send(test_msg)
    if success:
        print("SUCCESS: Test email sent successfully to", recipients)
    else:
        print("FAILED: Could not send test email. Check logs for details.")



def test_whatsapp(config: Dict[str, Any]) -> None:
    """Test Twilio WhatsApp configuration."""
    print("\n--- Testing WhatsApp Notification ---")
    wa_cfg = config.get("notification", {}).get("whatsapp", {})
    sid = wa_cfg.get("account_sid", "")
    from_num = wa_cfg.get("from_number", "")
    to_num = wa_cfg.get("to_number", "")

    print(f"Twilio Account SID: {sid[:6]}... (masked)")
    print(f"From Number: {from_num}")
    print(f"To Number: {to_num}")

    if not sid or not wa_cfg.get("auth_token"):
        print("ERROR: Twilio WhatsApp credentials are missing in .env or config.yaml")
        print("Please set TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN in your .env file.")
        return

    service = WhatsAppNotification(
        account_sid=sid,
        auth_token=wa_cfg.get("auth_token", ""),
        from_number=from_num,
        to_number=to_num
    )

    test_msg = NotificationMessage(
        ps_id="TEST-SIH",
        ps_title="Test WhatsApp Alert Verification",
        previous_count=10,
        current_count=15,
        increase=5,
        detected_at=datetime.datetime.now().strftime("%d %b %Y, %I:%M %p"),
        portal_url=config.get("sih", {}).get("url", "https://sih.gov.in/sih2026PS"),
        source="Test Execution"
    )

    success = service.send(test_msg)
    if success:
        print("SUCCESS: Test WhatsApp message sent successfully to", to_num)
    else:
        print("FAILED: Could not send WhatsApp message. Check logs for details.")


def print_status(db_path: str = "sih_monitor.db") -> None:
    """Print database monitoring status and history summary."""
    print("\n" + "=" * 65)
    print("SIH PROBLEM STATEMENT MONITOR - STATUS REPORT")
    print("=" * 65)

    if not os.path.exists(db_path):
        print(f"Database file '{db_path}' does not exist yet. Run a check cycle first.")
        return

    db = DatabaseManager(db_path)
    summary = db.get_all_monitored_summary()

    if not summary:
        print("No problem statements have been recorded in the database yet.")
        return

    print(f"{'PS ID':<12} | {'Latest Count':<14} | {'Total Checks':<14} | {'Last Checked'}")
    print("-" * 65)
    for row in summary:
        print(f"{row['ps_id']:<12} | {row['latest_count']:<14} | {row['total_checks']:<14} | {row['checked_at']}")

    print("\nRecent Alert Notifications Sent:")
    print("-" * 65)
    for row in summary:
        last_notif = db.get_last_notification(row["ps_id"])
        if last_notif:
            print(f"PS {row['ps_id']}: {last_notif['previous_count']} -> {last_notif['new_count']} (+{last_notif['increase']}) at {last_notif['notified_at']} via {last_notif['channels']}")
        else:
            print(f"PS {row['ps_id']}: No alert notifications sent yet.")
    print("=" * 65 + "\n")


def print_health(db_path: str = "sih_monitor.db") -> None:
    """Generate JSON health status output (Requirement #14)."""
    db = DatabaseManager(db_path)
    summary = db.get_all_monitored_summary()
    latest_check = max([r["checked_at"] for r in summary], default=None) if summary else None

    health_data = {
        "status": "healthy",
        "last_check": latest_check or datetime.datetime.now().isoformat(),
        "monitored_ps": len(summary),
        "database": os.path.abspath(db_path)
    }
    print(json.dumps(health_data, indent=2))


def run_web_server(port: int, monitor: SihMonitor, db: DatabaseManager):
    """Run a lightweight HTTP server responding to health checks on Render/cloud."""
    class MonitorHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path in ("/", "/health"):
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                summary = db.get_all_monitored_summary()
                latest_check = max([r["checked_at"] for r in summary], default=None) if summary else None
                data = {
                    "status": "healthy",
                    "mode": "continuous_monitor",
                    "interval_seconds": monitor.interval,
                    "last_check": latest_check or monitor.last_check_timestamp,
                    "monitored_ps_count": len(summary),
                    "database_backend": "PostgreSQL" if db.is_postgres else "SQLite"
                }
                self.wfile.write(json.dumps(data, indent=2).encode("utf-8"))
            elif self.path == "/check-now":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                results = monitor.run_check_cycle()
                self.wfile.write(json.dumps({
                    "status": "ok",
                    "checked": len(results),
                    "results": results
                }, indent=2).encode("utf-8"))
            else:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b'{"error": "Not Found"}')

        def log_message(self, format, *args):
            # Suppress noisy HTTP access logs
            return

    server = HTTPServer(("0.0.0.0", port), MonitorHandler)
    logger = logging.getLogger("sih_monitor.web")
    logger.info("Cloud Web Server listening on 0.0.0.0:%d", port)
    server.serve_forever()


def list_portal_ps(config: Dict[str, Any]) -> None:

    """Discover and list all problem statements available on the portal."""
    portal_url = config.get("sih", {}).get("url", "https://sih.gov.in/sih2026PS")
    scraper_type = config.get("monitor", {}).get("scraper_type", "html")
    scraper = get_scraper(scraper_type=scraper_type, portal_url=portal_url)

    print(f"\nFetching problem statements from {portal_url}...")
    data = scraper.fetch_all()
    print(f"\nTotal problem statements found: {len(data)}\n")
    print(f"{'PS ID':<12} | {'Count':<10} | {'Category':<10} | {'Title'}")
    print("-" * 80)
    for ps_id, item in list(data.items())[:30]:
        title = item['title'][:45] + "..." if len(item['title']) > 45 else item['title']
        print(f"{ps_id:<12} | {item['raw_count']:<10} | {item['category']:<10} | {title}")

    if len(data) > 30:
        print(f"\n... and {len(data) - 30} more problem statements available on the portal.")


def main():
    parser = argparse.ArgumentParser(
        description="Smart India Hackathon (SIH) Problem Statement Count Monitor"
    )
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml (default: config.yaml)")
    parser.add_argument("--check-now", action="store_true", help="Perform exactly one check cycle and exit")
    parser.add_argument("--dry-run", action="store_true", help="Perform check without saving or sending alerts")
    parser.add_argument("--simulate-increase", type=int, default=0, help="Simulate a count increase by N (useful with --dry-run)")
    parser.add_argument("--test-email", action="store_true", help="Send a test email notification to verify SMTP")
    parser.add_argument("--test-whatsapp", action="store_true", help="Send a test WhatsApp message to verify Twilio")
    parser.add_argument("--status", action="store_true", help="Display current monitoring database status")
    parser.add_argument("--health", action="store_true", help="Display JSON health check status")
    parser.add_argument("--list-ps", action="store_true", help="List problem statements discovered on the portal")
    parser.add_argument("--serve", action="store_true", help="Launch background web server alongside monitor (auto-enabled if PORT env var is present)")

    args = parser.parse_args()



    setup_logging()
    logger = logging.getLogger("sih_monitor.main")

    try:
        config = load_configuration(args.config)
    except Exception as e:
        logger.error("Failed to load configuration: %s", e)
        sys.exit(1)

    db_path = config.get("database", {}).get("path", "sih_monitor.db")
    db = DatabaseManager(db_path)

    # CLI command routing
    if args.status:
        print_status(db_path)
        return

    if args.health:
        print_health(db_path)
        return

    if args.test_email:
        test_email(config)
        return

    if args.test_whatsapp:
        test_whatsapp(config)
        return

    if args.list_ps:
        list_portal_ps(config)
        return

    # Initialize scraper & dispatcher
    portal_url = config.get("sih", {}).get("url", "https://sih.gov.in/sih2026PS")
    scraper_type = config.get("monitor", {}).get("scraper_type", "html")
    timeout = config.get("monitor", {}).get("request_timeout_seconds", 30)

    scraper = get_scraper(scraper_type=scraper_type, portal_url=portal_url, timeout=timeout)
    dispatcher = build_notification_dispatcher(config)

    monitor = SihMonitor(
        config=config,
        scraper=scraper,
        db=db,
        dispatcher=dispatcher,
        dry_run=args.dry_run,
        simulate_increase=args.simulate_increase
    )


    if args.check_now:
        logger.info("Executing single check cycle (--check-now)...")
        results = monitor.run_check_cycle()
        print(f"\nCompleted single check for {len(results)} problem statement(s).")
        return

    # If running on Render (where PORT is injected) or if --serve is explicitly requested
    port_env = os.getenv("PORT")
    if args.serve or port_env:
        port = int(port_env) if port_env else 8080
        server_thread = threading.Thread(
            target=run_web_server,
            args=(port, monitor, db),
            daemon=True
        )
        server_thread.start()
        logger.info("Started cloud web server thread on port %d", port)

    # Default: Run continuous loop
    monitor.run_forever()



if __name__ == "__main__":
    main()
