from __future__ import annotations

from copy import deepcopy

from app.policy import DecisionKind, evaluate_duplicate_group


def asset(
    asset_id: str,
    filename: str,
    *,
    mime: str,
    width: int = 4032,
    height: int = 3024,
    taken: str | None = "2024-05-01T12:34:56.000Z",
    make: str | None = "Apple",
    model: str | None = "iPhone 15 Pro",
    latitude: float | None = 54.0,
    longitude: float | None = -1.0,
    live_photo_video_id: str | None = None,
    is_edited: bool = False,
    is_offline: bool = False,
    is_trashed: bool = False,
    stack=None,
    size: int = 1_000_000,
):
    return {
        "id": asset_id,
        "ownerId": "11111111-1111-4111-8111-111111111111",
        "type": "IMAGE",
        "originalFileName": filename,
        "originalPath": f"/usr/src/app/external/{filename}",
        "originalMimeType": mime,
        "width": width,
        "height": height,
        "localDateTime": taken,
        "fileCreatedAt": taken,
        "fileModifiedAt": taken,
        "createdAt": taken,
        "updatedAt": taken,
        "duration": None,
        "livePhotoVideoId": live_photo_video_id,
        "isEdited": is_edited,
        "isOffline": is_offline,
        "isTrashed": is_trashed,
        "stack": stack,
        "exifInfo": {
            "dateTimeOriginal": taken,
            "make": make,
            "model": model,
            "latitude": latitude,
            "longitude": longitude,
            "fileSizeInByte": size,
            "exifImageWidth": width,
            "exifImageHeight": height,
        },
    }


def group(heic=None, jpeg=None, *, assets=None):
    return {
        "duplicateId": "22222222-2222-4222-8222-222222222222",
        "assets": assets if assets is not None else [
            heic or asset("heic-id", "IMG_0001.HEIC", mime="image/heic", size=1_500_000),
            jpeg or asset("jpeg-id", "IMG_0001.JPG", mime="image/jpeg", size=3_500_000),
        ],
        "suggestedKeepAssetIds": ["jpeg-id"],
    }


def test_safe_pair_prefers_heic_even_if_immich_suggests_jpeg():
    decision = evaluate_duplicate_group(group())

    assert decision.kind is DecisionKind.SAFE_HEIC_CANDIDATE
    assert decision.keep_asset_id == "heic-id"
    assert decision.trash_asset_id == "jpeg-id"
    assert decision.reasons == ()
    assert decision.evidence["immich_suggested_keep_asset_ids"] == ["jpeg-id"]
    assert decision.evidence["heic_bytes"] == 1_500_000
    assert decision.evidence["jpeg_bytes"] == 3_500_000


def test_heif_and_jpeg_extensions_are_supported_case_insensitively():
    heif = asset("heif-id", "holiday.HeIf", mime="image/heif")
    jpeg = asset("jpeg-id", "holiday.JpEg", mime="image/jpeg")

    decision = evaluate_duplicate_group(group(heic=heif, jpeg=jpeg))

    assert decision.kind is DecisionKind.SAFE_HEIC_CANDIDATE
    assert decision.keep_asset_id == "heif-id"


def test_conflicting_mime_and_extension_requires_review():
    heic = asset("heic-id", "IMG_0001.HEIC", mime="image/jpeg")
    jpeg = asset("jpeg-id", "IMG_0001.JPG", mime="image/jpeg")

    decision = evaluate_duplicate_group(group(heic=heic, jpeg=jpeg))

    assert decision.kind is DecisionKind.REVIEW
    assert "not_exact_heic_jpeg_pair" in decision.reasons


def test_group_must_be_exactly_one_heic_and_one_jpeg():
    assets = [
        asset("heic-1", "IMG_1.HEIC", mime="image/heic"),
        asset("jpeg-1", "IMG_1.JPG", mime="image/jpeg"),
        asset("jpeg-2", "IMG_1-copy.JPG", mime="image/jpeg"),
    ]

    decision = evaluate_duplicate_group(group(assets=assets))

    assert decision.kind is DecisionKind.REVIEW
    assert "not_exact_heic_jpeg_pair" in decision.reasons


def test_stems_must_match():
    heic = asset("heic-id", "IMG_0001.HEIC", mime="image/heic")
    jpeg = asset("jpeg-id", "exported-copy.JPG", mime="image/jpeg")

    decision = evaluate_duplicate_group(group(heic=heic, jpeg=jpeg))

    assert decision.kind is DecisionKind.REVIEW
    assert "filename_stem_mismatch" in decision.reasons


def test_dimensions_must_match_and_must_be_known():
    jpeg = asset("jpeg-id", "IMG_0001.JPG", mime="image/jpeg", width=1920, height=1080)
    decision = evaluate_duplicate_group(group(jpeg=jpeg))
    assert decision.kind is DecisionKind.REVIEW
    assert "dimension_mismatch" in decision.reasons

    heic = asset("heic-id", "IMG_0001.HEIC", mime="image/heic")
    jpeg = asset("jpeg-id", "IMG_0001.JPG", mime="image/jpeg")
    heic["width"] = heic["height"] = None
    heic["exifInfo"]["exifImageWidth"] = heic["exifInfo"]["exifImageHeight"] = None
    decision = evaluate_duplicate_group(group(heic=heic, jpeg=jpeg))
    assert "missing_dimensions" in decision.reasons


def test_capture_times_must_be_within_two_seconds():
    jpeg = asset(
        "jpeg-id",
        "IMG_0001.JPG",
        mime="image/jpeg",
        taken="2024-05-01T12:34:59.500Z",
    )

    decision = evaluate_duplicate_group(group(jpeg=jpeg))

    assert decision.kind is DecisionKind.REVIEW
    assert "capture_time_mismatch" in decision.reasons


def test_missing_capture_time_requires_review():
    heic = asset("heic-id", "IMG_0001.HEIC", mime="image/heic", taken=None)

    decision = evaluate_duplicate_group(group(heic=heic))

    assert decision.kind is DecisionKind.REVIEW
    assert "missing_capture_time" in decision.reasons


def test_conflicting_camera_identity_requires_review_but_missing_camera_data_does_not():
    jpeg = asset("jpeg-id", "IMG_0001.JPG", mime="image/jpeg", model="Different Camera")
    decision = evaluate_duplicate_group(group(jpeg=jpeg))
    assert "camera_mismatch" in decision.reasons

    heic = asset("heic-id", "IMG_0001.HEIC", mime="image/heic", make=None, model=None)
    decision = evaluate_duplicate_group(group(heic=heic))
    assert "camera_mismatch" not in decision.reasons


def test_conflicting_gps_requires_review_but_missing_gps_does_not():
    jpeg = asset(
        "jpeg-id",
        "IMG_0001.JPG",
        mime="image/jpeg",
        latitude=55.0,
        longitude=-1.0,
    )
    decision = evaluate_duplicate_group(group(jpeg=jpeg))
    assert "gps_mismatch" in decision.reasons

    heic = asset(
        "heic-id",
        "IMG_0001.HEIC",
        mime="image/heic",
        latitude=None,
        longitude=None,
    )
    decision = evaluate_duplicate_group(group(heic=heic))
    assert "gps_mismatch" not in decision.reasons


def test_live_photo_edited_offline_trashed_or_stacked_assets_require_review():
    mutators = [
        ("live_photo_asset", lambda a: a.__setitem__("livePhotoVideoId", "video-id")),
        ("edited_asset", lambda a: a.__setitem__("isEdited", True)),
        ("offline_asset", lambda a: a.__setitem__("isOffline", True)),
        ("trashed_asset", lambda a: a.__setitem__("isTrashed", True)),
        ("stacked_asset", lambda a: a.__setitem__("stack", {"id": "stack-id"})),
    ]

    for reason, mutate in mutators:
        heic = asset("heic-id", "IMG_0001.HEIC", mime="image/heic")
        mutate(heic)
        decision = evaluate_duplicate_group(group(heic=heic))
        assert decision.kind is DecisionKind.REVIEW
        assert reason in decision.reasons


def test_cross_owner_group_requires_review():
    heic = asset("heic-id", "IMG_0001.HEIC", mime="image/heic")
    jpeg = asset("jpeg-id", "IMG_0001.JPG", mime="image/jpeg")
    jpeg["ownerId"] = "33333333-3333-4333-8333-333333333333"

    decision = evaluate_duplicate_group(group(heic=heic, jpeg=jpeg))

    assert decision.kind is DecisionKind.REVIEW
    assert "owner_mismatch" in decision.reasons


def test_review_evidence_summarises_every_asset_even_when_group_is_not_exact_pair():
    assets = [
        asset("heic-1", "IMG_1.HEIC", mime="image/heic", live_photo_video_id="video-1"),
        asset("jpeg-1", "IMG_1.JPG", mime="image/jpeg"),
        asset("jpeg-2", "IMG_1-copy.JPG", mime="image/jpeg", width=2048, height=1536),
    ]

    decision = evaluate_duplicate_group(group(assets=assets))

    assert decision.kind is DecisionKind.REVIEW
    assert decision.reasons == ("not_exact_heic_jpeg_pair",)
    assert decision.evidence["asset_count"] == 3
    assert decision.evidence["assets"] == [
        {
            "id": "heic-1",
            "filename": "IMG_1.HEIC",
            "mime_type": "image/heic",
            "format": "heic",
            "type": "IMAGE",
            "dimensions": [4032, 3024],
            "bytes": 1_000_000,
            "capture_time": "2024-05-01T12:34:56",
            "live_photo_video_id": "video-1",
            "is_edited": False,
            "is_offline": False,
            "is_trashed": False,
            "stacked": False,
        },
        {
            "id": "jpeg-1",
            "filename": "IMG_1.JPG",
            "mime_type": "image/jpeg",
            "format": "jpeg",
            "type": "IMAGE",
            "dimensions": [4032, 3024],
            "bytes": 1_000_000,
            "capture_time": "2024-05-01T12:34:56",
            "live_photo_video_id": None,
            "is_edited": False,
            "is_offline": False,
            "is_trashed": False,
            "stacked": False,
        },
        {
            "id": "jpeg-2",
            "filename": "IMG_1-copy.JPG",
            "mime_type": "image/jpeg",
            "format": "jpeg",
            "type": "IMAGE",
            "dimensions": [2048, 1536],
            "bytes": 1_000_000,
            "capture_time": "2024-05-01T12:34:56",
            "live_photo_video_id": None,
            "is_edited": False,
            "is_offline": False,
            "is_trashed": False,
            "stacked": False,
        },
    ]


def test_exact_pair_evidence_identifies_which_asset_has_live_photo_relationship():
    heic = asset(
        "heic-id",
        "IMG_0001.HEIC",
        mime="image/heic",
        live_photo_video_id="video-id",
    )

    decision = evaluate_duplicate_group(group(heic=heic))

    assert decision.kind is DecisionKind.REVIEW
    assert "live_photo_asset" in decision.reasons
    summaries = {item["id"]: item for item in decision.evidence["assets"]}
    assert summaries["heic-id"]["live_photo_video_id"] == "video-id"
    assert summaries["jpeg-id"]["live_photo_video_id"] is None
