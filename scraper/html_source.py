import re
import logging
from typing import Dict, Optional, Any
import requests
import urllib3
from bs4 import BeautifulSoup

from .base import BaseScraper

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
logger = logging.getLogger("sih_monitor.scraper.html")


class HtmlSource(BaseScraper):
    """
    Scraper that fetches the SIH portal HTML and extracts problem statement
    records from the server-rendered `#dataTablePS` data table.
    """

    DEFAULT_USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )

    def __init__(self, portal_url: str, timeout: int = 30):
        super().__init__(portal_url=portal_url, timeout=timeout)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": self.DEFAULT_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        })

    def fetch_all(self) -> Dict[str, Dict[str, Any]]:
        """
        Request the SIH portal page, parse the `#dataTablePS` table, and extract all PS items.
        """
        logger.info("Fetching SIH portal from %s", self.portal_url)
        try:
            resp = self.session.get(self.portal_url, timeout=self.timeout, verify=False)
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.error("HTTP request to SIH portal failed: %s", e)
            raise ConnectionError(f"Failed to connect to SIH portal: {e}") from e

        soup = BeautifulSoup(resp.content, "html.parser")
        
        # Locate the problem statement data table
        table = soup.find("table", {"id": "dataTablePS"})
        if not table:
            # Fallback search for any table containing 'PS Number' or 'Submitted Idea'
            tables = soup.find_all("table")
            for t in tables:
                headers = [th.get_text(strip=True) for th in t.find_all("th")]
                if any("PS Number" in h for h in headers) or any("Submitted Idea" in h for h in headers):
                    table = t
                    break

        if not table:
            error_msg = "Could not find problem statement table (#dataTablePS) in SIH HTML response."
            logger.error(error_msg)
            raise ValueError(error_msg)

        tbody = table.find("tbody")
        rows = tbody.find_all("tr", recursive=False) if tbody else table.find_all("tr", recursive=False)

        results: Dict[str, Dict[str, Any]] = {}

        for row in rows:
            tds = row.find_all("td", recursive=False)
            if len(tds) < 6:
                continue

            sno = tds[0].get_text(strip=True)
            organization = tds[1].get_text(strip=True)
            
            # Title cell often contains an <a> tag linking to modal details
            title_tag = tds[2].find("a")
            if title_tag:
                title = title_tag.get_text(strip=True)
            else:
                title = tds[2].get_text(strip=True).split("Problem Statement Details")[0].strip()

            category = tds[3].get_text(strip=True) if len(tds) > 3 else ""
            ps_number = tds[4].get_text(strip=True) if len(tds) > 4 else ""
            count_raw = tds[5].get_text(strip=True) if len(tds) > 5 else "0"
            theme = tds[6].get_text(strip=True) if len(tds) > 6 else ""
            deadline = tds[7].get_text(strip=True) if len(tds) > 7 else ""

            if not ps_number:
                continue

            # Parse count string: e.g. "203/500" -> current=203, capacity=500
            # or plain "42" -> current=42
            m = re.search(r"(\d+)\s*(?:/\s*(\d+))?", count_raw)
            if m:
                current_count = int(m.group(1))
                max_capacity = int(m.group(2)) if m.group(2) else None
            else:
                logger.warning("Unrecognized count format '%s' for PS %s; defaulting to 0", count_raw, ps_number)
                current_count = 0
                max_capacity = None

            normalized_id = ps_number.strip().upper()
            results[normalized_id] = {
                "ps_id": normalized_id,
                "title": title,
                "current_count": current_count,
                "max_capacity": max_capacity,
                "raw_count": count_raw,
                "category": category,
                "organization": organization,
                "theme": theme,
                "deadline": deadline,
                "sno": sno,
                "source": "html"
            }

        logger.info("Successfully extracted %d problem statements from SIH portal.", len(results))
        return results
