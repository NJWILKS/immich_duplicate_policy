from __future__ import annotations

from typing import Any

import requests


class ImmichClientError(RuntimeError):
    pass


def normalise_api_url(url: str) -> str:
    base = url.strip().rstrip("/")
    if base.endswith("/api"):
        return base
    return f"{base}/api"


class ImmichClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        session: requests.Session | None = None,
        timeout_seconds: int = 30,
    ) -> None:
        if not base_url.strip():
            raise ValueError("Immich URL is required")
        if not api_key.strip():
            raise ValueError("Immich API key is required")

        self.base_url = normalise_api_url(base_url)
        self._api_key = api_key
        self._session = session or requests.Session()
        self.timeout_seconds = timeout_seconds

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "x-api-key": self._api_key,
        }

    def get_duplicates(self) -> list[dict[str, Any]]:
        url = f"{self.base_url}/duplicates"
        try:
            response = self._session.get(
                url,
                headers=self._headers(),
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise ImmichClientError(
                f"Immich duplicate API request failed at {url}"
            ) from exc

        if not isinstance(payload, list):
            raise ImmichClientError(
                "Immich duplicate API returned an unexpected payload; expected a JSON array"
            )

        return payload
