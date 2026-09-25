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

    def _headers(self, *, json_body: bool = False) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "x-api-key": self._api_key,
        }
        if json_body:
            headers["Content-Type"] = "application/json"
        return headers

    def _get_json(self, path: str) -> Any:
        url = f"{self.base_url}{path}"
        try:
            response = self._session.get(
                url,
                headers=self._headers(),
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            raise ImmichClientError(f"Immich API request failed at {url}") from exc

    def _post_json(self, path: str, payload: dict[str, Any]) -> Any:
        url = f"{self.base_url}{path}"
        try:
            response = self._session.post(
                url,
                headers=self._headers(json_body=True),
                json=payload,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            raise ImmichClientError(f"Immich API request failed at {url}") from exc

    def get_duplicates(self) -> list[dict[str, Any]]:
        payload = self._get_json("/duplicates")
        if not isinstance(payload, list):
            raise ImmichClientError(
                "Immich duplicate API returned an unexpected payload; expected a JSON array"
            )
        return payload

    def get_server_features(self) -> dict[str, Any]:
        payload = self._get_json("/server/features")
        if not isinstance(payload, dict):
            raise ImmichClientError(
                "Immich server features API returned an unexpected payload; expected a JSON object"
            )
        if not isinstance(payload.get("trash"), bool):
            raise ImmichClientError(
                "Immich server features API did not return the required boolean trash flag"
            )
        return payload

    def resolve_duplicates(
        self,
        groups: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        payload = self._post_json("/duplicates/resolve", {"groups": groups})
        if not isinstance(payload, list):
            raise ImmichClientError(
                "Immich duplicate resolve API returned an unexpected payload; expected a JSON array"
            )
        return payload
