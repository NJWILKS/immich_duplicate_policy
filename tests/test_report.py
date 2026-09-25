from __future__ import annotations

import json

from app.policy import Decision, DecisionKind
from app.report import decision_to_record


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
