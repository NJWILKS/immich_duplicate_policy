from __future__ import annotations

import json

from app.policy import Decision, DecisionKind
from app.report import build_review_diagnostics, decision_to_record


def test_decision_record_is_stable_and_auditable():
    decision = Decision(
        duplicate_id="group-1",
        kind=DecisionKind.SAFE_HEIC_CANDIDATE,
        keep_asset_id="heic-1",
        trash_asset_id="jpeg-1",
        reasons=(),
        evidence={
            "heic_filename": "IMG_1.HEIC",
            "jpeg_filename": "IMG_1.JPG",
            "immich_suggested_keep_asset_ids": ["jpeg-1"],
        },
    )

    record = decision_to_record(decision)

    assert record["duplicate_id"] == "group-1"
    assert record["decision"] == "SAFE_HEIC_CANDIDATE"
    assert record["keep_asset_id"] == "heic-1"
    assert record["trash_asset_id"] == "jpeg-1"
    assert record["reasons"] == []
    json.dumps(record)



def test_review_diagnostics_describes_group_shape_without_changing_policy():
    decisions = [
        Decision(
            duplicate_id="two-jpegs",
            kind=DecisionKind.REVIEW,
            keep_asset_id=None,
            trash_asset_id=None,
            reasons=("not_exact_heic_jpeg_pair",),
            evidence={
                "asset_count": 2,
                "assets": [
                    {"filename": "IMG_1.JPG", "format": "jpeg", "type": "IMAGE"},
                    {"filename": "IMG_1.jpeg", "format": "jpeg", "type": "IMAGE"},
                ],
            },
        ),
        Decision(
            duplicate_id="heic-video",
            kind=DecisionKind.REVIEW,
            keep_asset_id=None,
            trash_asset_id=None,
            reasons=("not_exact_heic_jpeg_pair",),
            evidence={
                "asset_count": 2,
                "assets": [
                    {"filename": "IMG_2.HEIC", "format": "heic", "type": "IMAGE"},
                    {"filename": "IMG_2.MOV", "format": None, "type": "VIDEO"},
                ],
            },
        ),
        Decision(
            duplicate_id="three-assets",
            kind=DecisionKind.REVIEW,
            keep_asset_id=None,
            trash_asset_id=None,
            reasons=("not_exact_heic_jpeg_pair",),
            evidence={
                "asset_count": 3,
                "assets": [
                    {"filename": "A.JPG", "format": "jpeg", "type": "IMAGE"},
                    {"filename": "B.JPG", "format": "jpeg", "type": "IMAGE"},
                    {"filename": "C.HEIC", "format": "heic", "type": "IMAGE"},
                ],
            },
        ),
        Decision(
            duplicate_id="ordinary-review",
            kind=DecisionKind.REVIEW,
            keep_asset_id=None,
            trash_asset_id=None,
            reasons=("filename_stem_mismatch",),
            evidence={
                "asset_count": 2,
                "assets": [
                    {"filename": "A.HEIC", "format": "heic", "type": "IMAGE"},
                    {"filename": "B.JPG", "format": "jpeg", "type": "IMAGE"},
                ],
            },
        ),
    ]

    diagnostics = build_review_diagnostics(decisions)

    assert diagnostics["review_groups"] == 4
    assert diagnostics["asset_count"] == {"2": 3, "3": 1}
    assert diagnostics["format_composition"] == {
        "1xheic+1xjpeg": 1,
        "1xheic+1xother": 1,
        "1xheic+2xjpeg": 1,
        "2xjpeg": 1,
    }
    assert diagnostics["media_type_composition"] == {
        "1ximage+1xvideo": 1,
        "2ximage": 2,
        "3ximage": 1,
    }
    assert diagnostics["two_asset_filename_stems"] == {
        "different": 1,
        "same": 2,
    }

    subset = diagnostics["not_exact_heic_jpeg_pair"]
    assert subset["groups"] == 3
    assert subset["asset_count"] == {"2": 2, "3": 1}
    assert subset["format_composition"] == {
        "1xheic+1xother": 1,
        "1xheic+2xjpeg": 1,
        "2xjpeg": 1,
    }
    assert subset["media_type_composition"] == {
        "1ximage+1xvideo": 1,
        "2ximage": 1,
        "3ximage": 1,
    }
    assert subset["two_asset_filename_stems"] == {
        "same": 2,
    }
