"""Scraper package for SIH PS Monitor."""
from .base import BaseScraper
from .html_source import HtmlSource
from .api_source import ApiSource
from .browser_source import BrowserSource


def get_scraper(scraper_type: str = "html", portal_url: str = "", timeout: int = 30, **kwargs) -> BaseScraper:
    """Factory function to instantiate the desired scraper implementation."""
    stype = scraper_type.lower().strip()
    if stype == "html":
        return HtmlSource(portal_url=portal_url, timeout=timeout)
    elif stype == "api":
        return ApiSource(portal_url=portal_url, timeout=timeout, **kwargs)
    elif stype == "browser":
        return BrowserSource(portal_url=portal_url, timeout=timeout)
    else:
        raise ValueError(f"Unknown scraper_type '{scraper_type}'. Supported: 'html', 'api', 'browser'.")


__all__ = ["BaseScraper", "HtmlSource", "ApiSource", "BrowserSource", "get_scraper"]
