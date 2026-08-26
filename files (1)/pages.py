"""Page-level operations on top of ConfluenceAPI.

The raw REST payloads are deeply nested and differ between Server/DC and
Cloud. Everything above this layer should consume the flat dict that
normalise_page() returns, never the raw response.
"""

from src.utils_v2.confluence.confluence import ConfluenceAPI
from src.utils_v2.confluence.exceptions import ConfluenceException
from src.utils_v2.logger import shared_logger

logger = shared_logger(__name__)


def normalise_page(raw, base_url=""):
    """Flatten a Confluence content payload into the shape the validator wants."""
    version = raw.get("version") or {}
    history = raw.get("history") or {}
    last_updated = history.get("lastUpdated") or {}
    space = raw.get("space") or {}
    metadata = raw.get("metadata") or {}
    labels_block = (metadata.get("labels") or {}).get("results") or []
    links = raw.get("_links") or {}

    webui = links.get("webui") or ""
    url = f"{base_url.rstrip('/')}{webui}" if webui and base_url else webui

    return {
        "page_id": str(raw.get("id") or ""),
        "title": raw.get("title") or "",
        "type": raw.get("type") or "",
        "status": raw.get("status") or "",
        "space_key": space.get("key") or "",
        "space_name": space.get("name") or "",
        "version": version.get("number"),
        "last_updated": last_updated.get("when") or version.get("when") or "",
        "last_updated_by": (
            (last_updated.get("by") or version.get("by") or {}).get("displayName") or ""
        ),
        "created_by": ((history.get("createdBy") or {}).get("displayName") or ""),
        "created_date": history.get("createdDate") or "",
        "labels": [lbl.get("name") for lbl in labels_block if lbl.get("name")],
        "url": url,
    }


class PagesAPI:
    """Fetch and normalise the Confluence pages referenced by a change request."""

    def __init__(self, api):
        if not isinstance(api, ConfluenceAPI):
            raise ConfluenceException("PagesAPI requires a ConfluenceAPI instance")
        self.api = api

    async def get_page(self, page_id):
        raw = await self.api.get_content(page_id)
        return normalise_page(raw, base_url=self.api.base_url)

    async def get_page_by_title(self, space_key, title):
        raw = await self.api.get_page_by_title(space_key, title)
        return normalise_page(raw, base_url=self.api.base_url)

    async def resolve(self, ref):
        """Resolve one page reference produced by confluence_utils.extract_page_refs().

        ref is either {"page_id": "12345"} or {"space_key": "CAB", "title": "..."}.
        """
        if ref.get("page_id"):
            return await self.get_page(ref["page_id"])
        if ref.get("space_key") and ref.get("title"):
            return await self.get_page_by_title(ref["space_key"], ref["title"])
        raise ConfluenceException(f"Unresolvable Confluence reference: {ref}")
