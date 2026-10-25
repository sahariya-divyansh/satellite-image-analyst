"""Bhoonidhi (ISRO / NRSC Open Data Portal) catalog adapter.

Reference: ISRO / NRSC Bhoonidhi Open Search & STAC Interface.
Supports discovery of Indian Earth Observation assets (Resourcesat-2/2A AWiFS/LISS-3,
Cartosat-1/2, Oceansat) under Open Data policies.
"""

from typing import Any

from satellite_analyst.logging import get_logger
from satellite_analyst.planner.schema import BoundingBox, TimeInterval

logger = get_logger(__name__)

BHOONIDHI_API_BASE = "https://bhoonidhi.nrsc.gov.in/bhoonidhi/api"


class BhoonidhiAdapter:
    """Adapter for querying and authenticating against ISRO Bhoonidhi catalog.

    Note: Requires NRSC user credentials or an active token for full payload downloads.
    """

    def __init__(
        self,
        api_base: str = BHOONIDHI_API_BASE,
        token: str | None = None,
    ) -> None:
        self.api_base = api_base
        self.token = token

    def search_products(
        self,
        satellite: str,  # e.g., "RESOURCESAT-2A", "CARTOSAT-1"
        sensor: str,  # e.g., "AWIFS", "LISS-3"
        bbox: BoundingBox,
        time_range: TimeInterval,
    ) -> list[dict[str, Any]]:
        """Query Bhoonidhi metadata catalog for available granules."""
        logger.info(
            f"Querying Bhoonidhi for {satellite} {sensor} over bbox={bbox.as_list()} "
            f"between {time_range.start_date} and {time_range.end_date}"
        )
        # Stub for future ISRO API integration
        return []
