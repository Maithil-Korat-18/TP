import time
import datetime
import logging
from typing import Dict, List, Optional, Any, Tuple

from database.db import DatabaseManager
from scraper.base import BaseScraper
from notifications.base import NotificationMessage
from notifications import NotificationDispatcher

logger = logging.getLogger("sih_monitor.monitor")


class ChangeResult:
    BASELINE = "BASELINE"
    INCREASED = "INCREASED"
    UNCHANGED = "UNCHANGED"
    DECREASED = "DECREASED"


class SihMonitor:
    """
    Core monitoring engine for Smart India Hackathon Problem Statements.
    Monitors single or multiple PS entries, tracks history, detects changes,
    and coordinates alert notifications.
    """

    RETRY_DELAYS = [0, 5, 15, 30, 60]

    def __init__(
        self,
        config: dict,
        scraper: BaseScraper,
        db: DatabaseManager,
        dispatcher: NotificationDispatcher,
        dry_run: bool = False,
        simulate_increase: int = 0
    ):
        self.config = config
        self.scraper = scraper
        self.db = db
        self.dispatcher = dispatcher
        self.dry_run = dry_run
        self.simulate_increase = simulate_increase

        monitor_cfg = config.get("monitor", {})
        self.interval = monitor_cfg.get("interval_seconds", 300)
        self.max_retries = monitor_cfg.get("max_retries", 5)


        notif_cfg = config.get("notification", {})
        self.cooldown_seconds = notif_cfg.get("cooldown_seconds", 300)

        self.last_check_timestamp: Optional[str] = None
        self._target_ps_list = self._resolve_target_ps()

    def _resolve_target_ps(self) -> List[Dict[str, Any]]:
        """Extract all enabled problem statements from config."""
        targets = []
        # Multi-PS format
        ps_list = self.config.get("problem_statements", [])
        for item in ps_list:
            if item.get("enabled", True):
                targets.append({
                    "id": str(item.get("id", "")).strip().upper(),
                    "title": str(item.get("title", "")).strip(),
                })

        # Fallback to single 'sih' section if no problem_statements configured
        if not targets:
            sih_cfg = self.config.get("sih", {})
            single_id = sih_cfg.get("ps_id")
            if single_id:
                targets.append({
                    "id": str(single_id).strip().upper(),
                    "title": str(sih_cfg.get("ps_title", "")).strip(),
                })

        if not targets:
            logger.warning("No enabled problem statements defined in configuration.")

        return targets

    def fetch_with_retry(self) -> Dict[str, Dict[str, Any]]:
        """
        Fetch problem statements data from scraper using exponential backoff retry.
        """
        last_error = None
        for attempt, delay in enumerate(self.RETRY_DELAYS[: self.max_retries]):
            if delay > 0:
                logger.warning("Retrying portal fetch in %d seconds (attempt %d/%d)...", delay, attempt + 1, self.max_retries)
                time.sleep(delay)
            try:
                data = self.scraper.fetch_all()
                if data:
                    return data
                logger.warning("Scraper returned empty data on attempt %d", attempt + 1)
            except Exception as e:
                logger.error("Scraper fetch error on attempt %d: %s", attempt + 1, e)
                last_error = e

        raise ConnectionError(f"Failed to fetch data from SIH after {self.max_retries} attempts: {last_error}")

    def get_current_count(self, all_ps_data: Dict[str, Dict[str, Any]], ps_id: str) -> Optional[Dict[str, Any]]:
        """Lookup current count record for given ps_id."""
        normalized_target = ps_id.strip().upper()
        if normalized_target in all_ps_data:
            return all_ps_data[normalized_target]

        # Flexible matching
        clean_target = normalized_target.replace("SIH", "")
        for key, item in all_ps_data.items():
            if key.replace("SIH", "") == clean_target:
                return item

        return None

    def get_previous_count(self, ps_id: str) -> Optional[int]:
        """Fetch the most recent count for ps_id from the database."""
        return self.db.get_previous_count(ps_id)

    def detect_change(self, ps_id: str, current_count: int, previous_count: Optional[int]) -> Tuple[str, int]:
        """
        Evaluate count transition:
        - None -> 37: BASELINE (no notification)
        - 37 -> 42: INCREASED (+5 notification)
        - 42 -> 42: UNCHANGED (no notification)
        - 42 -> 40: DECREASED (warning logged, no notification)
        """
        if previous_count is None:
            return ChangeResult.BASELINE, 0

        diff = current_count - previous_count
        if diff > 0:
            return ChangeResult.INCREASED, diff
        elif diff == 0:
            return ChangeResult.UNCHANGED, 0
        else:
            logger.warning("PS count decreased for %s from %d to %d", ps_id, previous_count, current_count)
            return ChangeResult.DECREASED, diff

    def check_ps(
        self,
        target: Dict[str, Any],
        all_ps_data: Dict[str, Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """
        Check a single problem statement, detect changes, and trigger alerts.
        """
        ps_id = target["id"]
        configured_title = target.get("title", "")
        
        logger.info("Checking SIH PS %s", ps_id)
        current_data = self.get_current_count(all_ps_data, ps_id)

        if not current_data:
            logger.error("Problem Statement %s not found on the SIH portal! Verify PS ID.", ps_id)
            return None

        current_count = current_data["current_count"]
        if self.simulate_increase > 0:
            current_count += self.simulate_increase

        actual_title = current_data.get("title") or configured_title
        raw_count = current_data.get("raw_count", str(current_count))
        source = current_data.get("source", "html")


        logger.info("Current count for %s: %d (display: %s)", ps_id, current_count, raw_count)

        previous_count = self.get_previous_count(ps_id)
        change_type, diff = self.detect_change(ps_id, current_count, previous_count)

        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        formatted_time = datetime.datetime.now().strftime("%d %b %Y, %I:%M %p")

        # Create alert message object
        portal_url = self.config.get("sih", {}).get("url", "https://sih.gov.in/sih2026PS")
        message = NotificationMessage(
            ps_id=ps_id,
            ps_title=actual_title,
            previous_count=previous_count,
            current_count=current_count,
            increase=diff,
            detected_at=formatted_time,
            portal_url=portal_url,
            source="SIH Portal"
        )

        result_summary = {
            "ps_id": ps_id,
            "title": actual_title,
            "previous_count": previous_count,
            "current_count": current_count,
            "raw_count": raw_count,
            "change_type": change_type,
            "increase": diff,
            "checked_at": now_str,
            "dry_run": self.dry_run
        }

        if change_type == ChangeResult.BASELINE:
            logger.info("First execution for %s: Baseline count recorded as %d", ps_id, current_count)
            if not self.dry_run:
                self.db.save_count(ps_id, actual_title, current_count, source=source, checked_at=now_str)

        elif change_type == ChangeResult.INCREASED:
            logger.info("Count increased for %s: %d -> %d (+%d)", ps_id, previous_count, current_count, diff)
            
            # Check cooldown and duplicate prevention
            in_cooldown = self.db.is_in_cooldown(ps_id, self.cooldown_seconds)
            if in_cooldown:
                logger.warning("Alert for %s suppressed by cooldown (%d seconds).", ps_id, self.cooldown_seconds)
            else:
                if self.dry_run:
                    email_enabled = self.config.get("notification", {}).get("email", {}).get("enabled", False)
                    wa_enabled = self.config.get("notification", {}).get("whatsapp", {}).get("enabled", False)
                    print("\n" + "=" * 50)
                    print("DRY RUN: CHANGE DETECTED")
                    print(f"PS: {ps_id} - {actual_title}")
                    print(f"Previous count: {previous_count}")
                    print(f"Current count: {current_count}")
                    print(f"Increase: +{diff}")
                    print(f"Would send: Email -> {'enabled' if email_enabled else 'disabled'}, WhatsApp -> {'enabled' if wa_enabled else 'disabled'}")
                    print("=" * 50 + "\n")
                else:
                    # Save new count first
                    self.db.save_count(ps_id, actual_title, current_count, source=source, checked_at=now_str)
                    # Broadcast notifications
                    try:
                        broadcast_results = self.dispatcher.broadcast(message)
                        channels = ",".join([k for k, v in broadcast_results.items() if v]) or "none"
                    except Exception as e:
                        logger.error("Failed to broadcast alert for %s: %s", ps_id, e)
                        channels = "failed"
                    self.db.record_notification(ps_id, previous_count, current_count, channels=channels, status="sent" if channels != "failed" else "failed")


        elif change_type == ChangeResult.UNCHANGED:
            logger.info("Count unchanged for %s: %d", ps_id, current_count)
            # Record observation in history without triggering notification
            if not self.dry_run:
                self.db.save_count(ps_id, actual_title, current_count, source=source, checked_at=now_str)

        elif change_type == ChangeResult.DECREASED:
            logger.warning("Count decreased for %s: %d -> %d. Notification skipped.", ps_id, previous_count, current_count)
            if not self.dry_run:
                self.db.save_count(ps_id, actual_title, current_count, source=source, checked_at=now_str)

        return result_summary

    def run_check_cycle(self) -> List[Dict[str, Any]]:
        """
        Execute one full check cycle across all monitored problem statements.
        Handles errors gracefully to prevent crashes.
        """
        cycle_start = datetime.datetime.now().isoformat()
        self.last_check_timestamp = cycle_start
        logger.info("Starting SIH check cycle at %s", cycle_start)

        try:
            all_ps_data = self.fetch_with_retry()
        except Exception as e:
            logger.error("Failed to retrieve SIH counts during check cycle: %s", e)
            return []

        results = []
        for target in self._target_ps_list:
            try:
                res = self.check_ps(target, all_ps_data)
                if res:
                    results.append(res)
            except Exception as e:
                logger.error("Error processing PS %s: %s", target.get("id"), e, exc_info=True)

        logger.info("Completed check cycle. Monitored %d PS entries.", len(results))
        return results

    def run_forever(self) -> None:
        """
        Continuously run the monitoring loop at configured intervals.
        Handles unexpected exceptions to ensure uninterrupted execution.
        """
        logger.info("Starting SIH Monitor continuous loop (interval: %d seconds)...", self.interval)
        try:
            while True:
                try:
                    self.run_check_cycle()
                except Exception as e:
                    logger.error("Unhandled error in check cycle: %s", e, exc_info=True)

                logger.info("Sleeping for %d seconds until next check...", self.interval)
                time.sleep(self.interval)
        except KeyboardInterrupt:
            logger.info("Monitoring loop stopped by user (Ctrl+C).")
