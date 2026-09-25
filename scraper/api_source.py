import logging
from typing import Dict, Optional, Any
import requests
from .base import BaseScraper

logger = logging.getLogger("sih_monitor.scraper.api")


class ApiSource(BaseScraper):
    """
    Adapter for REST/JSON API endpoints if SIH exposes or provides an official endpoint.
    """

    def __init__(self, portal_url: str, timeout: int = 30, api_key: Optional[str] = None):
        super().__init__(portal_url=portal_url, timeout=timeout)
        self.api_key = api_key
        self.session = requests.Session()
        if self.api_key:
            self.session.headers.update({"Authorization": f"Bearer {self.api_key}"})

    def fetch_all(self) -> Dict[str, Dict[str, Any]]:
        logger.info("Querying SIH API endpoint at %s", self.portal_url)
        try:
            resp = self.session.get(self.portal_url, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.error("API request failed: %s", e)
            raise ConnectionError(f"API source error: {e}") from e

        results: Dict[str, Dict[str, Any]] = {}
        items = data if isinstance(data, list) else data.get("data", data.get("items", []))

        for item in items:
            ps_id = str(item.get("ps_id") or item.get("id") or item.get("ps_number", "")).strip().upper()
            if not ps_id:
                continue
            
            count_val = item.get("count") or item.get("submitted_count") or item.get("submissions", 0)
            try:
                count_int = int(count_val)
            except (ValueError, TypeError):
                count_int = 0

            results[ps_id] = {
                "ps_id": ps_id,
                "title": item.get("title", item.get("ps_title", "")),
                "current_count": count_int,
                "max_capacity": item.get("max_capacity"),
                "raw_count": str(count_val),
                "category": item.get("category", ""),
                "organization": item.get("organization", ""),
                "theme": item.get("theme", ""),
                "deadline": item.get("deadline", ""),
                "source": "api"
            }

        return results
