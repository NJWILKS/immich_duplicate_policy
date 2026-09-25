from __future__ import annotations

import json

from app.main import apply_once, main, scan_once


class FakeClient:
    def get_duplicates(self):
        return [
            {
                "duplicateId": "group-1",
                "assets": [
                    {
                        "id": "heic-1",
                        "ownerId": "owner-1",
                        "type": "IMAGE",
                        "originalFileName": "IMG_1.HEIC",
                        "originalMimeType": "image/heic",
                        "width": 100,
                        "height": 100,
                        "localDateTime": "2024-01-01T12:00:00Z",
                        "fileCreatedAt": "2024-01-01T12:00:00Z",
                        "livePhotoVideoId": None,
                        "isEdited": False,
                        "isOffline": False,
                        "isTrashed": False,
                        "stack": None,
                        "exifInfo": {
                            "dateTimeOriginal": "2024-01-01T12:00:00Z",
                            "fileSizeInByte": 100,
                            "make": "Apple",
                            "model": "iPhone",
                            "latitude": 54.0,
                            "longitude": -1.0,
                        },
                    },
                    {
                        "id": "jpeg-1",
                        "ownerId": "owner-1",
                        "type": "IMAGE",
                        "originalFileName": "IMG_1.JPG",
                        "originalMimeType": "image/jpeg",
                        "width": 100,
                        "height": 100,
                        "localDateTime": "2024-01-01T12:00:00Z",
                        "fileCreatedAt": "2024-01-01T12:00:00Z",
                        "livePhotoVideoId": None,
                        "isEdited": False,
                        "isOffline": False,
                        "isTrashed": False,
                        "stack": None,
                        "exifInfo": {
                            "dateTimeOriginal": "2024-01-01T12:00:00Z",
                            "fileSizeInByte": 200,
                            "make": "Apple",
                            "model": "iPhone",
                            "latitude": 54.0,
                            "longitude": -1.0,
                        },
                    },
                ],
                "suggestedKeepAssetIds": ["jpeg-1"],
            }
        ]


def test_scan_writes_latest_snapshot_and_append_only_audit(tmp_path):
    scan_once(FakeClient(), tmp_path)
    scan_once(FakeClient(), tmp_path)

    latest = json.loads((tmp_path / "latest.json").read_text())
    assert latest["duplicate_groups"] == 1
    assert latest["decisions"][0]["decision"] == "SAFE_HEIC_CANDIDATE"
    assert latest["decisions"][0]["keep_asset_id"] == "heic-1"
    assert latest["summary"]["decisions"] == {
        "SAFE_HEIC_CANDIDATE": 1,
        "REVIEW": 0,
    }
    assert latest["summary"]["safe_basis"] == {"exact_pair": 1}
    assert latest["summary"]["review_reasons"] == {}

    lines = (tmp_path / "decisions.jsonl").read_text().splitlines()
    assert len(lines) == 2
    assert all(json.loads(line)["duplicate_id"] == "group-1" for line in lines)


class FakeApplyClient:
    def __init__(self, *, trash_enabled=True, results=None):
        self.trash_enabled = trash_enabled
        self.results = results
        self.resolve_calls = []
        self.get_duplicates_calls = 0

    def get_server_features(self):
        return {"trash": self.trash_enabled}

    def get_duplicates(self):
        self.get_duplicates_calls += 1
        if self.get_duplicates_calls == 1:
            return [
                *FakeClient().get_duplicates(),
                {
                    "duplicateId": "review-group",
                    "assets": [
                        {
                            **FakeClient().get_duplicates()[0]["assets"][0],
                            "id": "review-heic",
                            "originalFileName": "A.HEIC",
                        },
                        {
                            **FakeClient().get_duplicates()[0]["assets"][1],
                            "id": "review-jpeg",
                            "originalFileName": "B.JPG",
                        },
                    ],
                    "suggestedKeepAssetIds": ["review-jpeg"],
                },
            ]
        return [
            {
                "duplicateId": "review-group",
                "assets": [
                    {
                        **FakeClient().get_duplicates()[0]["assets"][0],
                        "id": "review-heic",
                        "originalFileName": "A.HEIC",
                    },
                    {
                        **FakeClient().get_duplicates()[0]["assets"][1],
                        "id": "review-jpeg",
                        "originalFileName": "B.JPG",
                    },
                ],
                "suggestedKeepAssetIds": ["review-jpeg"],
            }
        ]

    def resolve_duplicates(self, groups):
        self.resolve_calls.append(groups)
        if self.results is not None:
            return self.results
        return [{"id": group["duplicateId"], "success": True} for group in groups]


def test_apply_refuses_to_run_if_immich_trash_is_disabled(tmp_path):
    client = FakeApplyClient(trash_enabled=False)

    result = apply_once(client, tmp_path, batch_size=100)

    assert result == 2
    assert client.resolve_calls == []


def test_apply_rechecks_live_duplicates_and_resolves_only_safe_candidates(tmp_path):
    client = FakeApplyClient()

    result = apply_once(client, tmp_path, batch_size=100)

    assert result == 0
    assert client.resolve_calls == [[
        {
            "duplicateId": "group-1",
            "keepAssetIds": ["heic-1"],
            "trashAssetIds": ["jpeg-1"],
        }
    ]]

    audit = json.loads((tmp_path / "last_apply.json").read_text())
    assert audit["candidate_count"] == 1
    assert audit["success_count"] == 1
    assert audit["failure_count"] == 0
    assert audit["actions"][0]["duplicate_id"] == "group-1"
    assert audit["actions"][0]["keep_asset_id"] == "heic-1"
    assert audit["actions"][0]["trash_asset_id"] == "jpeg-1"
    assert audit["actions"][0]["result"]["success"] is True

    latest = json.loads((tmp_path / "latest.json").read_text())
    assert latest["duplicate_groups"] == 1
    assert latest["summary"]["decisions"]["SAFE_HEIC_CANDIDATE"] == 0
    assert latest["summary"]["decisions"]["REVIEW"] == 1


def test_apply_batches_all_candidates_and_returns_failure_if_any_group_fails(tmp_path):
    client = FakeApplyClient(
        results=[{"id": "group-1", "success": False, "error": "UNKNOWN"}]
    )

    result = apply_once(client, tmp_path, batch_size=1)

    assert result == 1
    audit = json.loads((tmp_path / "last_apply.json").read_text())
    assert audit["candidate_count"] == 1
    assert audit["success_count"] == 0
    assert audit["failure_count"] == 1


def test_main_accepts_apply_mode_as_one_shot(monkeypatch, tmp_path):
    monkeypatch.setenv("MODE", "apply")
    monkeypatch.setenv("IMMICH_URL", "https://photos.example.test")
    monkeypatch.setenv("IMMICH_API_KEY", "secret")
    monkeypatch.setenv("STATE_DIR", str(tmp_path))

    calls = []

    class MainClient(FakeApplyClient):
        def __init__(self, *args, **kwargs):
            calls.append((args, kwargs))
            super().__init__()

    monkeypatch.setattr("app.main.ImmichClient", MainClient)

    assert main() == 0
    assert len(calls) == 1
