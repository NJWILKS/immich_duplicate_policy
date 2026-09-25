from __future__ import annotations

import json
import os
import sys
import time
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from app.immich_client import ImmichClient, ImmichClientError
from app.policy import DecisionKind, evaluate_duplicate_group
from app.report import decision_to_record


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc


def scan_once(client: ImmichClient, state_dir: Path) -> int:
    started = datetime.now(timezone.utc)
    run_id = str(uuid.uuid4())

    groups = client.get_duplicates()
    decisions = [evaluate_duplicate_group(group) for group in groups]

    state_dir.mkdir(parents=True, exist_ok=True)
    latest_path = state_dir / "latest.json"
    audit_path = state_dir / "decisions.jsonl"

    records = []
    for decision in decisions:
        record = decision_to_record(decision)
        record["run_id"] = run_id
        record["scanned_at"] = started.isoformat()
        records.append(record)

    counts = Counter(decision.kind.value for decision in decisions)
    safe_basis_counts = Counter(
        basis
        for decision in decisions
        if decision.kind is DecisionKind.SAFE_HEIC_CANDIDATE
        for basis in decision.evidence.get("safe_basis", [])
    )
    review_reason_counts = Counter(
        reason
        for decision in decisions
        if decision.kind is DecisionKind.REVIEW
        for reason in decision.reasons
    )

    latest_payload = {
        "run_id": run_id,
        "scanned_at": started.isoformat(),
        "duplicate_groups": len(groups),
        "summary": {
            "decisions": {
                DecisionKind.SAFE_HEIC_CANDIDATE.value: counts[DecisionKind.SAFE_HEIC_CANDIDATE.value],
                DecisionKind.REVIEW.value: counts[DecisionKind.REVIEW.value],
            },
            "safe_basis": dict(sorted(safe_basis_counts.items())),
            "review_reasons": dict(sorted(review_reason_counts.items())),
        },
        "decisions": records,
    }
    latest_path.write_text(
        json.dumps(latest_payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    with audit_path.open("a", encoding="utf-8") as audit:
        for record in records:
            audit.write(json.dumps(record, ensure_ascii=False) + "\n")

    safe = counts[DecisionKind.SAFE_HEIC_CANDIDATE.value]
    review = counts[DecisionKind.REVIEW.value]

    print(
        f"Scanned {len(groups):,} duplicate groups: "
        f"{safe:,} SAFE_HEIC_CANDIDATE, {review:,} REVIEW"
    )
    if safe_basis_counts:
        print(
            "Safe basis: "
            + ", ".join(f"{name}={count:,}" for name, count in sorted(safe_basis_counts.items()))
        )
    if review_reason_counts:
        print(
            "Review reasons: "
            + ", ".join(f"{name}={count:,}" for name, count in sorted(review_reason_counts.items()))
        )
    print(f"Latest report: {latest_path}")
    return len(groups)


def _chunks(items: list[dict], size: int):
    for start in range(0, len(items), size):
        yield items[start : start + size]


def apply_once(client: ImmichClient, state_dir: Path, *, batch_size: int = 100) -> int:
    state_dir.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc)
    apply_id = str(uuid.uuid4())

    features = client.get_server_features()
    if features.get("trash") is not True:
        print(
            "Refusing MODE=apply because Immich trash is disabled; "
            "duplicate resolution would permanently delete trashed assets.",
            file=sys.stderr,
        )
        return 2

    # Re-read and re-evaluate the live duplicate set immediately before mutation.
    groups = client.get_duplicates()
    decisions = [evaluate_duplicate_group(group) for group in groups]
    candidates = [
        decision
        for decision in decisions
        if decision.kind is DecisionKind.SAFE_HEIC_CANDIDATE
    ]

    requests_by_id: dict[str, dict] = {}
    candidate_by_id = {decision.duplicate_id: decision for decision in candidates}
    resolve_groups: list[dict] = []
    for decision in candidates:
        request = {
            "duplicateId": decision.duplicate_id,
            "keepAssetIds": [decision.keep_asset_id],
            "trashAssetIds": [decision.trash_asset_id],
        }
        requests_by_id[decision.duplicate_id] = request
        resolve_groups.append(request)

    print(
        f"Apply preflight: {len(groups):,} live duplicate groups, "
        f"{len(candidates):,} SAFE_HEIC_CANDIDATE"
    )
    print("Immich trash is enabled; resolving all safe candidates via /duplicates/resolve")

    results_by_id: dict[str, dict] = {}
    batch_error: str | None = None

    for batch_number, batch in enumerate(_chunks(resolve_groups, max(1, batch_size)), start=1):
        try:
            batch_results = client.resolve_duplicates(batch)
        except ImmichClientError as exc:
            batch_error = str(exc)
            print(
                f"Apply stopped at batch {batch_number}: {batch_error}",
                file=sys.stderr,
            )
            break

        for result in batch_results:
            result_id = str(result.get("id") or "")
            if result_id:
                results_by_id[result_id] = result

        print(
            f"Resolved batch {batch_number}: "
            f"{sum(1 for result in batch_results if result.get('success') is True):,}/"
            f"{len(batch):,} succeeded"
        )

    actions = []
    success_count = 0
    failure_count = 0
    for duplicate_id, request in requests_by_id.items():
        decision = candidate_by_id[duplicate_id]
        result = results_by_id.get(duplicate_id)
        if result is None:
            result = {
                "id": duplicate_id,
                "success": False,
                "error": "NO_RESULT",
                "errorMessage": batch_error or "Immich returned no result for this group",
            }

        if result.get("success") is True:
            success_count += 1
        else:
            failure_count += 1

        actions.append(
            {
                "duplicate_id": duplicate_id,
                "keep_asset_id": decision.keep_asset_id,
                "trash_asset_id": decision.trash_asset_id,
                "safe_basis": list(decision.evidence.get("safe_basis", [])),
                "request": request,
                "result": result,
            }
        )

    completed = datetime.now(timezone.utc)
    apply_payload = {
        "apply_id": apply_id,
        "started_at": started.isoformat(),
        "completed_at": completed.isoformat(),
        "source_duplicate_groups": len(groups),
        "candidate_count": len(candidates),
        "success_count": success_count,
        "failure_count": failure_count,
        "batch_size": max(1, batch_size),
        "trash_enabled": True,
        "actions": actions,
    }

    last_apply_path = state_dir / "last_apply.json"
    apply_history_path = state_dir / "apply_actions.jsonl"
    last_apply_path.write_text(
        json.dumps(apply_payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    with apply_history_path.open("a", encoding="utf-8") as audit:
        for action in actions:
            audit.write(
                json.dumps(
                    {
                        "apply_id": apply_id,
                        "started_at": started.isoformat(),
                        **action,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    print(
        f"Apply complete: {success_count:,} succeeded, {failure_count:,} failed. "
        f"Audit: {last_apply_path}"
    )

    # Always re-read Immich after mutation so latest.json describes the actual
    # remaining duplicate queue, not the pre-apply plan.
    scan_once(client, state_dir)

    return 0 if failure_count == 0 and batch_error is None else 1


def main() -> int:
    mode = os.getenv("MODE", "report").strip().casefold()
    if mode not in {"report", "apply"}:
        print("MODE must be either report or apply.", file=sys.stderr)
        return 2

    try:
        url = _required_env("IMMICH_URL")
        api_key = _required_env("IMMICH_API_KEY")
        interval = max(0, _int_env("SCAN_INTERVAL_SECONDS", 0))
        timeout = max(1, _int_env("IMMICH_TIMEOUT_SECONDS", 30))
        batch_size = max(1, _int_env("APPLY_BATCH_SIZE", 100))
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    state_dir = Path(os.getenv("STATE_DIR", "/state"))
    client = ImmichClient(url, api_key, timeout_seconds=timeout)

    if mode == "apply":
        # Apply is deliberately one-shot even when SCAN_INTERVAL_SECONDS is set.
        # The long-running compose service remains MODE=report.
        try:
            return apply_once(client, state_dir, batch_size=batch_size)
        except ImmichClientError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        except Exception as exc:
            print(f"Duplicate policy apply failed: {exc}", file=sys.stderr)
            return 1

    while True:
        try:
            scan_once(client, state_dir)
        except ImmichClientError as exc:
            print(str(exc), file=sys.stderr)
            if interval <= 0:
                return 1
        except Exception as exc:
            print(f"Duplicate policy scan failed: {exc}", file=sys.stderr)
            if interval <= 0:
                return 1

        if interval <= 0:
            return 0

        print(f"Next scan in {interval}s")
        time.sleep(interval)


if __name__ == "__main__":
    raise SystemExit(main())
