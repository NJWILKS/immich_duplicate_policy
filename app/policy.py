from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any


MAX_CAPTURE_DELTA_SECONDS = 2.0
MAX_GPS_DISTANCE_METRES = 25.0

HEIC_EXTENSIONS = {".heic", ".heif"}
JPEG_EXTENSIONS = {".jpg", ".jpeg"}
HEIC_MIME_TYPES = {"image/heic", "image/heif"}
JPEG_MIME_TYPES = {"image/jpeg", "image/jpg"}


class DecisionKind(str, Enum):
    SAFE_HEIC_CANDIDATE = "SAFE_HEIC_CANDIDATE"
    REVIEW = "REVIEW"


@dataclass(frozen=True)
class Decision:
    duplicate_id: str
    kind: DecisionKind
    keep_asset_id: str | None
    trash_asset_id: str | None
    reasons: tuple[str, ...]
    evidence: dict[str, Any]


def _normalise_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text.casefold() if text else None


def _format_of(asset: dict[str, Any]) -> str | None:
    mime = _normalise_text(asset.get("originalMimeType"))
    suffix = Path(str(asset.get("originalFileName") or "")).suffix.casefold()

    mime_kind = (
        "heic" if mime in HEIC_MIME_TYPES
        else "jpeg" if mime in JPEG_MIME_TYPES
        else None
    )
    suffix_kind = (
        "heic" if suffix in HEIC_EXTENSIONS
        else "jpeg" if suffix in JPEG_EXTENSIONS
        else None
    )

    if mime_kind and suffix_kind and mime_kind != suffix_kind:
        return "conflict"
    return mime_kind or suffix_kind


def _dimensions(asset: dict[str, Any]) -> tuple[int, int] | None:
    exif = asset.get("exifInfo") or {}

    width = asset.get("width") or exif.get("exifImageWidth")
    height = asset.get("height") or exif.get("exifImageHeight")

    try:
        width = int(width)
        height = int(height)
    except (TypeError, ValueError):
        return None

    if width <= 0 or height <= 0:
        return None

    return width, height


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None

    text = str(value).strip()
    if not text:
        return None

    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None

    # Immich's localDateTime is intentionally timezone-agnostic. For this
    # policy we compare the photographed wall-clock time, not UTC offsets.
    return parsed.replace(tzinfo=None)


def _capture_time(asset: dict[str, Any]) -> datetime | None:
    exif = asset.get("exifInfo") or {}
    for value in (
        exif.get("dateTimeOriginal"),
        asset.get("localDateTime"),
        asset.get("fileCreatedAt"),
    ):
        parsed = _parse_datetime(value)
        if parsed is not None:
            return parsed
    return None


def _file_size(asset: dict[str, Any]) -> int | None:
    exif = asset.get("exifInfo") or {}
    value = exif.get("fileSizeInByte")
    try:
        size = int(value)
    except (TypeError, ValueError):
        return None
    return size if size >= 0 else None


def _camera_identity(asset: dict[str, Any]) -> tuple[str | None, str | None]:
    exif = asset.get("exifInfo") or {}
    return _normalise_text(exif.get("make")), _normalise_text(exif.get("model"))


def _coordinates(asset: dict[str, Any]) -> tuple[float, float] | None:
    exif = asset.get("exifInfo") or {}
    lat = exif.get("latitude")
    lon = exif.get("longitude")

    if lat is None and lon is None:
        return None
    if lat is None or lon is None:
        raise ValueError("partial GPS coordinates")

    try:
        lat_f = float(lat)
        lon_f = float(lon)
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid GPS coordinates") from exc

    if not (-90 <= lat_f <= 90 and -180 <= lon_f <= 180):
        raise ValueError("invalid GPS coordinates")

    return lat_f, lon_f


def _distance_metres(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    d_lat = lat2 - lat1
    d_lon = lon2 - lon1

    hav = (
        math.sin(d_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(d_lon / 2) ** 2
    )
    return 2 * 6_371_000 * math.asin(min(1.0, math.sqrt(hav)))


def _different_known_text(left: str | None, right: str | None) -> bool:
    return left is not None and right is not None and left != right


def _append_once(reasons: list[str], reason: str) -> None:
    if reason not in reasons:
        reasons.append(reason)


def _asset_summary(asset: dict[str, Any]) -> dict[str, Any]:
    dimensions = _dimensions(asset)
    capture_time = _capture_time(asset)
    return {
        "id": asset.get("id"),
        "filename": str(asset.get("originalFileName") or ""),
        "mime_type": asset.get("originalMimeType"),
        "format": _format_of(asset),
        "type": asset.get("type"),
        "dimensions": list(dimensions) if dimensions else None,
        "bytes": _file_size(asset),
        "capture_time": capture_time.isoformat() if capture_time else None,
        "live_photo_video_id": asset.get("livePhotoVideoId"),
        "is_edited": bool(asset.get("isEdited")),
        "is_offline": bool(asset.get("isOffline")),
        "is_trashed": bool(asset.get("isTrashed")),
        "stacked": bool(asset.get("stack")),
    }


def evaluate_duplicate_group(group: dict[str, Any]) -> Decision:
    duplicate_id = str(group.get("duplicateId") or "")
    assets = list(group.get("assets") or [])
    suggested = list(group.get("suggestedKeepAssetIds") or [])

    evidence: dict[str, Any] = {
        "asset_count": len(assets),
        "immich_suggested_keep_asset_ids": suggested,
        "assets": [_asset_summary(asset) for asset in assets],
    }
    reasons: list[str] = []

    heic_assets = [asset for asset in assets if _format_of(asset) == "heic"]
    jpeg_assets = [asset for asset in assets if _format_of(asset) == "jpeg"]

    if len(assets) != 2 or len(heic_assets) != 1 or len(jpeg_assets) != 1:
        return Decision(
            duplicate_id=duplicate_id,
            kind=DecisionKind.REVIEW,
            keep_asset_id=None,
            trash_asset_id=None,
            reasons=("not_exact_heic_jpeg_pair",),
            evidence=evidence,
        )

    heic = heic_assets[0]
    jpeg = jpeg_assets[0]

    heic_name = str(heic.get("originalFileName") or "")
    jpeg_name = str(jpeg.get("originalFileName") or "")
    evidence.update(
        {
            "heic_asset_id": heic.get("id"),
            "jpeg_asset_id": jpeg.get("id"),
            "heic_filename": heic_name,
            "jpeg_filename": jpeg_name,
            "heic_bytes": _file_size(heic),
            "jpeg_bytes": _file_size(jpeg),
        }
    )

    if str(heic.get("type") or "").upper() != "IMAGE" or str(jpeg.get("type") or "").upper() != "IMAGE":
        _append_once(reasons, "non_image_asset")

    if Path(heic_name).stem.casefold() != Path(jpeg_name).stem.casefold():
        _append_once(reasons, "filename_stem_mismatch")

    heic_dimensions = _dimensions(heic)
    jpeg_dimensions = _dimensions(jpeg)
    evidence["heic_dimensions"] = list(heic_dimensions) if heic_dimensions else None
    evidence["jpeg_dimensions"] = list(jpeg_dimensions) if jpeg_dimensions else None

    if heic_dimensions is None or jpeg_dimensions is None:
        _append_once(reasons, "missing_dimensions")
    elif heic_dimensions != jpeg_dimensions:
        _append_once(reasons, "dimension_mismatch")

    heic_time = _capture_time(heic)
    jpeg_time = _capture_time(jpeg)
    if heic_time is None or jpeg_time is None:
        _append_once(reasons, "missing_capture_time")
        evidence["capture_delta_seconds"] = None
    else:
        delta = abs((heic_time - jpeg_time).total_seconds())
        evidence["capture_delta_seconds"] = delta
        if delta > MAX_CAPTURE_DELTA_SECONDS:
            _append_once(reasons, "capture_time_mismatch")

    heic_make, heic_model = _camera_identity(heic)
    jpeg_make, jpeg_model = _camera_identity(jpeg)
    if _different_known_text(heic_make, jpeg_make) or _different_known_text(heic_model, jpeg_model):
        _append_once(reasons, "camera_mismatch")

    try:
        heic_coords = _coordinates(heic)
        jpeg_coords = _coordinates(jpeg)
    except ValueError:
        heic_coords = jpeg_coords = None
        _append_once(reasons, "invalid_gps_data")
    else:
        if heic_coords is not None and jpeg_coords is not None:
            distance = _distance_metres(heic_coords, jpeg_coords)
            evidence["gps_distance_metres"] = round(distance, 3)
            if distance > MAX_GPS_DISTANCE_METRES:
                _append_once(reasons, "gps_mismatch")
        else:
            evidence["gps_distance_metres"] = None

    if heic.get("ownerId") != jpeg.get("ownerId"):
        _append_once(reasons, "owner_mismatch")

    for item in (heic, jpeg):
        if item.get("livePhotoVideoId"):
            _append_once(reasons, "live_photo_asset")
        if item.get("isEdited"):
            _append_once(reasons, "edited_asset")
        if item.get("isOffline"):
            _append_once(reasons, "offline_asset")
        if item.get("isTrashed"):
            _append_once(reasons, "trashed_asset")
        if item.get("stack"):
            _append_once(reasons, "stacked_asset")

    if reasons:
        return Decision(
            duplicate_id=duplicate_id,
            kind=DecisionKind.REVIEW,
            keep_asset_id=None,
            trash_asset_id=None,
            reasons=tuple(reasons),
            evidence=evidence,
        )

    return Decision(
        duplicate_id=duplicate_id,
        kind=DecisionKind.SAFE_HEIC_CANDIDATE,
        keep_asset_id=str(heic.get("id")),
        trash_asset_id=str(jpeg.get("id")),
        reasons=(),
        evidence=evidence,
    )
