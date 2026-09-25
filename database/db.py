import sqlite3
import datetime
import logging
import os
import re
from contextlib import contextmanager
from typing import Optional, List, Dict, Any, Generator

logger = logging.getLogger("sih_monitor.database")


class DatabaseManager:
    """
    Unified database manager supporting both SQLite (local) and PostgreSQL (cloud/Render).
    Automatically switches to PostgreSQL if DATABASE_URL environment variable is set.
    """

    def __init__(self, db_path: Optional[str] = None):
        env_db = os.getenv("DATABASE_URL")
        if env_db and (env_db.startswith("postgres://") or env_db.startswith("postgresql://")):
            # SQLAlchemy / psycopg2 compatibility: postgres:// -> postgresql://
            self.db_url = env_db.replace("postgres://", "postgresql://", 1)
            self.is_postgres = True
            self.db_path = self.db_url
        elif db_path and (db_path.startswith("postgres://") or db_path.startswith("postgresql://")):
            self.db_url = db_path.replace("postgres://", "postgresql://", 1)
            self.is_postgres = True
            self.db_path = self.db_url
        else:
            self.db_path = db_path or "sih_monitor.db"
            self.is_postgres = False

        self._init_db()

    @contextmanager
    def _get_connection(self) -> Generator[Any, None, None]:
        """Establish a database connection and ensure it is closed upon completion."""
        if self.is_postgres:
            import psycopg2
            from psycopg2.extras import RealDictCursor
            conn = psycopg2.connect(self.db_url, cursor_factory=RealDictCursor)
            try:
                yield conn
            finally:
                conn.close()
        else:
            conn = sqlite3.connect(self.db_path, timeout=10.0)
            conn.row_factory = sqlite3.Row
            try:
                yield conn
            finally:
                conn.close()

    def _param_format(self, query: str) -> str:
        """Replace ? with %s if using PostgreSQL."""
        if self.is_postgres:
            return query.replace("?", "%s")
        return query

    def _init_db(self) -> None:
        """Initialize database tables and indexes."""
        if not self.is_postgres:
            dirname = os.path.dirname(os.path.abspath(self.db_path))
            if dirname:
                os.makedirs(dirname, exist_ok=True)

        id_col_type = "SERIAL PRIMARY KEY" if self.is_postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    CREATE TABLE IF NOT EXISTS ps_count_history (
                        id {id_col_type},
                        ps_id TEXT NOT NULL,
                        ps_title TEXT,
                        count INTEGER NOT NULL,
                        checked_at TEXT NOT NULL,
                        source TEXT DEFAULT 'html'
                    )
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_ps_count_history_ps_id 
                    ON ps_count_history (ps_id, checked_at DESC)
                """)

                cursor.execute(f"""
                    CREATE TABLE IF NOT EXISTS ps_notification_history (
                        id {id_col_type},
                        ps_id TEXT NOT NULL,
                        previous_count INTEGER,
                        new_count INTEGER NOT NULL,
                        increase INTEGER NOT NULL,
                        channels TEXT NOT NULL,
                        notified_at TEXT NOT NULL,
                        status TEXT DEFAULT 'sent'
                    )
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_ps_notifications_ps_id 
                    ON ps_notification_history (ps_id, notified_at DESC)
                """)
                conn.commit()
                backend_name = "PostgreSQL" if self.is_postgres else f"SQLite ({self.db_path})"
                logger.debug("Database initialized successfully using %s", backend_name)
        except Exception as e:
            logger.error("Failed to initialize database: %s", e)
            raise

    def save_count(
        self,
        ps_id: str,
        ps_title: str,
        count: int,
        source: str = "html",
        checked_at: Optional[str] = None
    ) -> int:
        """Save a new count observation to ps_count_history."""
        if checked_at is None:
            checked_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        query = """
            INSERT INTO ps_count_history (ps_id, ps_title, count, checked_at, source)
            VALUES (?, ?, ?, ?, ?)
        """
        if self.is_postgres:
            query += " RETURNING id"

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    self._param_format(query),
                    (ps_id.strip(), ps_title.strip() if ps_title else "", count, checked_at, source)
                )
                if self.is_postgres:
                    row = cursor.fetchone()
                    row_id = row["id"] if isinstance(row, dict) else row[0]
                else:
                    row_id = cursor.lastrowid
                conn.commit()
                logger.debug("Saved count %d for %s (id=%d)", count, ps_id, row_id)
                return row_id
        except Exception as e:
            logger.error("Database error while saving count for %s: %s", ps_id, e)
            raise

    def get_latest_count(self, ps_id: str) -> Optional[int]:
        """Get the most recently recorded count for a given ps_id."""
        query = """
            SELECT count FROM ps_count_history
            WHERE ps_id = ?
            ORDER BY id DESC
            LIMIT 1
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(self._param_format(query), (ps_id.strip(),))
                row = cursor.fetchone()
                if not row:
                    return None
                return int(row["count"])
        except Exception as e:
            logger.error("Database error getting latest count for %s: %s", ps_id, e)
            return None

    def get_previous_count(self, ps_id: str) -> Optional[int]:
        """Alias for get_latest_count before a new observation is saved."""
        return self.get_latest_count(ps_id)

    def get_count_history(self, ps_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Retrieve recent count records for a problem statement."""
        query = """
            SELECT id, ps_id, ps_title, count, checked_at, source
            FROM ps_count_history
            WHERE ps_id = ?
            ORDER BY id DESC
            LIMIT ?
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(self._param_format(query), (ps_id.strip(), limit))
                rows = cursor.fetchall()
                return [dict(r) for r in rows]
        except Exception as e:
            logger.error("Database error fetching history for %s: %s", ps_id, e)
            return []

    def record_notification(
        self,
        ps_id: str,
        previous_count: Optional[int],
        new_count: int,
        channels: str,
        status: str = "sent"
    ) -> int:
        """Record an alert notification sent."""
        notified_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        increase = (new_count - previous_count) if previous_count is not None else 0

        query = """
            INSERT INTO ps_notification_history 
            (ps_id, previous_count, new_count, increase, channels, notified_at, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        if self.is_postgres:
            query += " RETURNING id"

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    self._param_format(query),
                    (ps_id.strip(), previous_count, new_count, increase, channels, notified_at, status)
                )
                if self.is_postgres:
                    row = cursor.fetchone()
                    row_id = row["id"] if isinstance(row, dict) else row[0]
                else:
                    row_id = cursor.lastrowid
                conn.commit()
                return row_id
        except Exception as e:
            logger.error("Database error recording notification for %s: %s", ps_id, e)
            raise

    def get_last_notification(self, ps_id: str) -> Optional[Dict[str, Any]]:
        """Get the most recent notification for a PS."""
        query = """
            SELECT * FROM ps_notification_history
            WHERE ps_id = ?
            ORDER BY id DESC
            LIMIT 1
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(self._param_format(query), (ps_id.strip(),))
                row = cursor.fetchone()
                return dict(row) if row else None
        except Exception as e:
            logger.error("Database error getting last notification for %s: %s", ps_id, e)
            return None

    def is_in_cooldown(self, ps_id: str, cooldown_seconds: int = 300) -> bool:
        """Check if an alert was already sent within the cooldown window."""
        last_notif = self.get_last_notification(ps_id)
        if not last_notif:
            return False

        try:
            notif_time = datetime.datetime.strptime(last_notif["notified_at"], "%Y-%m-%d %H:%M:%S")
            elapsed = (datetime.datetime.now() - notif_time).total_seconds()
            return elapsed < cooldown_seconds
        except Exception as e:
            logger.warning("Error checking cooldown timestamp: %s", e)
            return False

    def get_all_monitored_summary(self) -> List[Dict[str, Any]]:
        """Get a summary of all problem statements tracked in the database."""
        query = """
            SELECT h.ps_id, h.ps_title, h.count as latest_count, h.checked_at, h.source,
                   (SELECT COUNT(*) FROM ps_count_history WHERE ps_id = h.ps_id) as total_checks
            FROM ps_count_history h
            INNER JOIN (
                SELECT ps_id, MAX(id) as max_id
                FROM ps_count_history
                GROUP BY ps_id
            ) latest ON h.id = latest.max_id
            ORDER BY h.ps_id ASC
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query)
                rows = cursor.fetchall()
                return [dict(r) for r in rows]
        except Exception as e:
            logger.error("Database error getting summary: %s", e)
            return []
