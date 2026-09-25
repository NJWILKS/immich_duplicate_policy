from __future__ import annotations

import pytest

from app.immich_client import ImmichClient, ImmichClientError, normalise_api_url


class FakeResponse:
    def __init__(self, payload=None, *, status_code=200, text=""):
        self._payload = payload
        self.status_code = status_code
        self.text = text

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(f"{self.status_code} error")

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def get(self, url, *, headers, timeout):
        self.calls.append(("GET", url, headers, timeout, None))
        return self.response

    def post(self, url, *, headers, json, timeout):
        self.calls.append(("POST", url, headers, timeout, json))
        return self.response


def test_normalise_api_url_accepts_root_or_api_url():
    assert normalise_api_url("https://photos.example.test") == "https://photos.example.test/api"
    assert normalise_api_url("https://photos.example.test/") == "https://photos.example.test/api"
    assert normalise_api_url("https://photos.example.test/api") == "https://photos.example.test/api"
    assert normalise_api_url("https://photos.example.test/api/") == "https://photos.example.test/api"


def test_get_duplicates_uses_official_endpoint_and_api_key_header():
    response = FakeResponse([{"duplicateId": "group-1", "assets": [], "suggestedKeepAssetIds": []}])
    session = FakeSession(response)
    client = ImmichClient(
        "https://photos.example.test",
        "secret",
        session=session,
        timeout_seconds=12,
    )

    result = client.get_duplicates()

    assert result == response._payload
    assert session.calls == [
        (
            "GET",
            "https://photos.example.test/api/duplicates",
            {"Accept": "application/json", "x-api-key": "secret"},
            12,
            None,
        )
    ]


def test_get_duplicates_rejects_non_list_payload():
    session = FakeSession(FakeResponse({"unexpected": True}))
    client = ImmichClient("https://photos.example.test", "secret", session=session)

    with pytest.raises(ImmichClientError, match="expected a JSON array"):
        client.get_duplicates()


def test_get_duplicates_wraps_http_errors_without_leaking_api_key():
    session = FakeSession(FakeResponse(status_code=401, text="nope"))
    client = ImmichClient("https://photos.example.test", "super-secret", session=session)

    with pytest.raises(ImmichClientError) as exc:
        client.get_duplicates()

    assert "super-secret" not in str(exc.value)


def test_get_server_features_requires_boolean_trash_flag():
    session = FakeSession(FakeResponse({"trash": True, "duplicateDetection": True}))
    client = ImmichClient("https://photos.example.test", "secret", session=session)

    result = client.get_server_features()

    assert result["trash"] is True
    assert session.calls[0][0:2] == ("GET", "https://photos.example.test/api/server/features")

    bad = ImmichClient(
        "https://photos.example.test",
        "secret",
        session=FakeSession(FakeResponse({"duplicateDetection": True})),
    )
    with pytest.raises(ImmichClientError, match="trash"):
        bad.get_server_features()


def test_resolve_duplicates_posts_official_duplicate_resolve_payload():
    response = FakeResponse([{"id": "group-1", "success": True}])
    session = FakeSession(response)
    client = ImmichClient("https://photos.example.test", "secret", session=session)

    result = client.resolve_duplicates(
        [
            {
                "duplicateId": "group-1",
                "keepAssetIds": ["heic-1"],
                "trashAssetIds": ["jpeg-1"],
            }
        ]
    )

    assert result == [{"id": "group-1", "success": True}]
    assert session.calls == [
        (
            "POST",
            "https://photos.example.test/api/duplicates/resolve",
            {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "x-api-key": "secret",
            },
            30,
            {
                "groups": [
                    {
                        "duplicateId": "group-1",
                        "keepAssetIds": ["heic-1"],
                        "trashAssetIds": ["jpeg-1"],
                    }
                ]
            },
        )
    ]


def test_resolve_duplicates_rejects_unexpected_payload():
    session = FakeSession(FakeResponse({"success": True}))
    client = ImmichClient("https://photos.example.test", "secret", session=session)

    with pytest.raises(ImmichClientError, match="expected a JSON array"):
        client.resolve_duplicates(
            [
                {
                    "duplicateId": "group-1",
                    "keepAssetIds": ["heic-1"],
                    "trashAssetIds": ["jpeg-1"],
                }
            ]
        )
