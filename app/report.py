from __future__ import annotations

from typing import Any

from app.policy import Decision


def decision_to_record(decision: Decision) -> dict[str, Any]:
    return {
        "duplicate_id": decision.duplicate_id,
        "decision": decision.kind.value,
        "keep_asset_id": decision.keep_asset_id,
        "trash_asset_id": decision.trash_asset_id,
        "reasons": list(decision.reasons),
        "evidence": decision.evidence,
    }
