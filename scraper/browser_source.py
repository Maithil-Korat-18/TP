import logging
import re
from typing import Dict, Any
from bs4 import BeautifulSoup
from .base import BaseScraper

logger = logging.getLogger("sih_monitor.scraper.browser")


class BrowserSource(BaseScraper):
    """
    Playwright headless browser scraper fallback for dynamic/JS-rendered content.
    """

    def fetch_all(self) -> Dict[str, Dict[str, Any]]:
        logger.info("Launching Playwright browser to render %s", self.portal_url)
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as e:
            logger.error("Playwright package is not installed. Run: pip install playwright && playwright install")
            raise RuntimeError("Playwright is not installed.") from e

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            try:
                page.goto(self.portal_url, timeout=self.timeout * 1000, wait_until="networkidle")
                page.wait_for_selector("#dataTablePS", timeout=15000)
                content = page.content()
            finally:
                browser.close()

        soup = BeautifulSoup(content, "html.parser")
        table = soup.find("table", {"id": "dataTablePS"})
        if not table:
            raise ValueError("Browser rendered page but could not find #dataTablePS")

        tbody = table.find("tbody")
        rows = tbody.find_all("tr", recursive=False) if tbody else table.find_all("tr", recursive=False)
        results: Dict[str, Dict[str, Any]] = {}

        for row in rows:
            tds = row.find_all("td", recursive=False)
            if len(tds) < 6:
                continue

            sno = tds[0].get_text(strip=True)
            organization = tds[1].get_text(strip=True)
            title_tag = tds[2].find("a")
            title = title_tag.get_text(strip=True) if title_tag else tds[2].get_text(strip=True)
            category = tds[3].get_text(strip=True)
            ps_number = tds[4].get_text(strip=True)
            count_raw = tds[5].get_text(strip=True)
            theme = tds[6].get_text(strip=True) if len(tds) > 6 else ""
            deadline = tds[7].get_text(strip=True) if len(tds) > 7 else ""

            if not ps_number:
                continue

            m = re.search(r"(\d+)\s*(?:/\s*(\d+))?", count_raw)
            current_count = int(m.group(1)) if m else 0
            max_capacity = int(m.group(2)) if (m and m.group(2)) else None

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
                "source": "browser"
            }

        logger.info("Extracted %d items using BrowserSource.", len(results))
        return results
