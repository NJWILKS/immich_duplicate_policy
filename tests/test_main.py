from __future__ import annotations

import json

from app.main import main, scan_once


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


def test_v02_refuses_any_non_report_mode(monkeypatch):
    monkeypatch.setenv("MODE", "apply")

    assert main() == 2


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
