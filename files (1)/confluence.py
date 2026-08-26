"""Confluence REST client.

TARGET: Confluence Server / Data Center, /rest/api/content.

If Ally is on Confluence Cloud instead, three things change and nothing
else does:
    _API_ROOT            -> "/wiki/api/v2"
    get_content()        -> GET /pages/{id}?body-format=storage
    search_cql()         -> GET /pages?title=... (no CQL in v2)
Confirm which one you are on before wiring credentials. The base URL
tells you: *.atlassian.net means Cloud.

AUTH: unresolved, same open question as Jira. This supports both shapes.
    CONFLUENCE_AUTH_MODE=bearer  -> Authorization: Bearer <token>   (PAT, Server/DC)
    CONFLUENCE_AUTH_MODE=basic   -> Authorization: Basic <email:token>  (Cloud)
If CAB traffic has to route through Apigee like the other integrations,
swap _base_url for the Apigee host and add whatever client-id header the
gateway expects. Do not ship this until that is settled.
"""

import base64
import os

import httpx

from src.utils_v2.confluence.exceptions import (
    ConfluenceAuthError,
    ConfluenceConfigError,
    ConfluenceException,
    ConfluenceNotFoundError,
    ConfluenceRateLimitError,
)
from src.utils_v2.logger import shared_logger

logger = shared_logger(__name__)

_API_ROOT = "/rest/api"
_DEFAULT_TIMEOUT = 30.0
_MAX_RETRIES = 3


class ConfluenceAPI:
    """Thin async wrapper over the Confluence REST API.

    One instance per subagent run. Use as an async context manager so the
    underlying connection pool is closed.
    """

    def __init__(self, base_url=None, token=None, email=None, auth_mode=None, timeout=_DEFAULT_TIMEOUT):
        self.base_url = (base_url or os.getenv("CONFLUENCE_BASE_URL", "")).rstrip("/")
        self.token = token or os.getenv("CONFLUENCE_TOKEN", "")
        self.email = email or os.getenv("CONFLUENCE_EMAIL", "")
        self.auth_mode = (auth_mode or os.getenv("CONFLUENCE_AUTH_MODE", "bearer")).lower()
        self.timeout = timeout
        self._client = None

        if not self.base_url:
            raise ConfluenceConfigError("CONFLUENCE_BASE_URL is not set")
        if not self.token:
            raise ConfluenceConfigError("CONFLUENCE_TOKEN is not set")
        if self.auth_mode == "basic" and not self.email:
            raise ConfluenceConfigError("CONFLUENCE_EMAIL is required when CONFLUENCE_AUTH_MODE=basic")

    def _auth_header(self):
        if self.auth_mode == "basic":
            raw = f"{self.email}:{self.token}".encode("utf-8")
            return {"Authorization": f"Basic {base64.b64encode(raw).decode('ascii')}"}
        return {"Authorization": f"Bearer {self.token}"}

    async def __aenter__(self):
        headers = {"Accept": "application/json"}
        headers.update(self._auth_header())
        self._client = httpx.AsyncClient(
            base_url=f"{self.base_url}{_API_ROOT}",
            headers=headers,
            timeout=self.timeout,
        )
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _request(self, method, path, page_id=None, **kwargs):
        if self._client is None:
            raise ConfluenceException("ConfluenceAPI used outside an async context manager")

        last_exc = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                response = await self._client.request(method, path, **kwargs)
            except httpx.TimeoutException as exc:
                last_exc = exc
                logger.warning(f"Confluence timeout on {path} (attempt {attempt}/{_MAX_RETRIES})")
                continue
            except httpx.HTTPError as exc:
                raise ConfluenceException(f"Transport error calling {path}: {exc}", page_id=page_id)

            if response.status_code in (401, 403):
                raise ConfluenceAuthError(
                    "Confluence rejected the credentials or the space is not readable",
                    status_code=response.status_code,
                    page_id=page_id,
                )
            if response.status_code == 404:
                raise ConfluenceNotFoundError(
                    "Confluence content not found",
                    status_code=404,
                    page_id=page_id,
                )
            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                raise ConfluenceRateLimitError(
                    "Confluence rate limit hit",
                    retry_after=int(retry_after) if retry_after and retry_after.isdigit() else None,
                    status_code=429,
                    page_id=page_id,
                )
            if response.status_code >= 500:
                last_exc = ConfluenceException(
                    "Confluence server error",
                    status_code=response.status_code,
                    page_id=page_id,
                )
                logger.warning(
                    f"Confluence {response.status_code} on {path} (attempt {attempt}/{_MAX_RETRIES})"
                )
                continue
            if response.status_code >= 400:
                raise ConfluenceException(
                    f"Confluence request failed: {response.text[:200]}",
                    status_code=response.status_code,
                    page_id=page_id,
                )

            try:
                return response.json()
            except ValueError:
                raise ConfluenceException(
                    f"Confluence returned non-JSON for {path}",
                    status_code=response.status_code,
                    page_id=page_id,
                )

        if isinstance(last_exc, ConfluenceException):
            raise last_exc
        raise ConfluenceException(
            f"Confluence unreachable after {_MAX_RETRIES} attempts: {last_exc}",
            page_id=page_id,
        )

    async def get_content(self, page_id, expand=None):
        """Fetch one page by id.

        expand controls how much comes back. The default pulls the fields
        the evidence validator needs and nothing more, because page bodies
        are large and these run per CR.
        """
        expand = expand or "version,space,history,history.lastUpdated,metadata.labels"
        return await self._request(
            "GET",
            f"/content/{page_id}",
            page_id=page_id,
            params={"expand": expand},
        )

    async def search_cql(self, cql, limit=25, expand=None):
        """Run a CQL query. Server/DC only; Cloud v2 has no CQL endpoint."""
        params = {"cql": cql, "limit": limit}
        if expand:
            params["expand"] = expand
        return await self._request("GET", "/content/search", params=params)

    async def get_page_by_title(self, space_key, title, expand=None):
        """Resolve a page from a space key plus title.

        Needed because Server/DC /display/ URLs carry the title, not the id.
        """
        params = {
            "spaceKey": space_key,
            "title": title,
            "expand": expand or "version,space,history,history.lastUpdated,metadata.labels",
        }
        payload = await self._request("GET", "/content", params=params)
        results = payload.get("results") or []
        if not results:
            raise ConfluenceNotFoundError(
                f"No Confluence page titled {title!r} in space {space_key!r}",
                status_code=404,
            )
        return results[0]
