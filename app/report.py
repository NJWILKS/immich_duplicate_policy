from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from app.policy import Decision, DecisionKind


def decision_to_record(decision: Decision) -> dict[str, Any]:
    return {
        "duplicate_id": decision.duplicate_id,
        "decision": decision.kind.value,
        "keep_asset_id": decision.keep_asset_id,
        "trash_asset_id": decision.trash_asset_id,
        "reasons": list(decision.reasons),
        "evidence": decision.evidence,
    }


def _count_bucket(asset_count: int) -> str:
    return "4+" if asset_count >= 4 else str(asset_count)


def _composition(values: Iterable[str | None], *, unknown: str) -> str:
    counts = Counter((value or unknown).casefold() for value in values)
    parts = [f"{count}x{name}" for name, count in sorted(counts.items())]
    return "+".join(parts)


def _two_asset_stem_relation(assets: list[dict[str, Any]]) -> str | None:
    if len(assets) != 2:
        return None

    stems = []
    for asset in assets:
        filename = str(asset.get("filename") or "").strip()
        if not filename:
            return None
        stems.append(Path(filename).stem.casefold())

    return "same" if stems[0] == stems[1] else "different"


def _shape_summary(decisions: Iterable[Decision]) -> dict[str, Any]:
    asset_counts: Counter[str] = Counter()
    format_compositions: Counter[str] = Counter()
    type_compositions: Counter[str] = Counter()
    stem_relations: Counter[str] = Counter()
    groups = 0

    for decision in decisions:
        groups += 1
        assets = list(decision.evidence.get("assets") or [])
        count = int(decision.evidence.get("asset_count") or len(assets))
        asset_counts[_count_bucket(count)] += 1
        format_compositions[
            _composition(
                [asset.get("format") for asset in assets],
                unknown="other",
            )
        ] += 1
        type_compositions[
            _composition(
                [str(asset.get("type") or "").casefold() or None for asset in assets],
                unknown="unknown",
            )
        ] += 1

        relation = _two_asset_stem_relation(assets)
        if relation:
            stem_relations[relation] += 1

    return {
        "groups": groups,
        "asset_count": dict(sorted(asset_counts.items())),
        "format_composition": dict(sorted(format_compositions.items())),
        "media_type_composition": dict(sorted(type_compositions.items())),
        "two_asset_filename_stems": dict(sorted(stem_relations.items())),
    }


def build_review_diagnostics(decisions: Iterable[Decision]) -> dict[str, Any]:
    review = [
        decision
        for decision in decisions
        if decision.kind is DecisionKind.REVIEW
    ]
    not_exact = [
        decision
        for decision in review
        if "not_exact_heic_jpeg_pair" in decision.reasons
    ]

    overall = _shape_summary(review)
    subset = _shape_summary(not_exact)

    return {
        "review_groups": overall.pop("groups"),
        **overall,
        "not_exact_heic_jpeg_pair": subset,
    }
