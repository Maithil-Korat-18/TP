"""Base scraper interface and data-source factory for SIH PS Monitor."""
from abc import ABC, abstractmethod
from typing import Dict, Optional, Any


class BaseScraper(ABC):
    """Abstract base class defining the contract for all SIH data source scrapers."""

    def __init__(self, portal_url: str, timeout: int = 30):
        self.portal_url = portal_url
        self.timeout = timeout

    @abstractmethod
    def fetch_all(self) -> Dict[str, Dict[str, Any]]:
        """
        Fetch all problem statements available on the portal.

        Returns:
            Dict mapping ps_id (e.g. 'SIH26001') to a dictionary of:
            {
                'ps_id': str,
                'title': str,
                'current_count': int,
                'max_capacity': Optional[int],
                'raw_count': str,
                'category': str,
                'organization': str,
                'theme': str,
                'deadline': str
            }
        """
        pass

    def get_count_for_ps(self, ps_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve data and count for a specific problem statement ID.
        Handles case-insensitive and prefix-insensitive matching.
        """
        all_data = self.fetch_all()
        normalized_target = ps_id.strip().upper()
        
        # Direct lookup
        if normalized_target in all_data:
            return all_data[normalized_target]
        
        # Flexible match (e.g. '26002' matching 'SIH26002')
        for key, item in all_data.items():
            if key == normalized_target or key.replace("SIH", "") == normalized_target.replace("SIH", ""):
                return item
        return None
