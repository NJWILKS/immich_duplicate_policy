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

    latest_payload = {
        "run_id": run_id,
        "scanned_at": started.isoformat(),
        "duplicate_groups": len(groups),
        "decisions": records,
    }
    latest_path.write_text(
        json.dumps(latest_payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    with audit_path.open("a", encoding="utf-8") as audit:
        for record in records:
            audit.write(json.dumps(record, ensure_ascii=False) + "\n")

    counts = Counter(decision.kind.value for decision in decisions)
    safe = counts[DecisionKind.SAFE_HEIC_CANDIDATE.value]
    review = counts[DecisionKind.REVIEW.value]

    print(
        f"Scanned {len(groups):,} duplicate groups: "
        f"{safe:,} SAFE_HEIC_CANDIDATE, {review:,} REVIEW"
    )
    print(f"Latest report: {latest_path}")
    return len(groups)


def main() -> int:
    mode = os.getenv("MODE", "report").strip().casefold()
    if mode != "report":
        print(
            "Only MODE=report is supported in v0.1; this build cannot modify Immich.",
            file=sys.stderr,
        )
        return 2

    try:
        url = _required_env("IMMICH_URL")
        api_key = _required_env("IMMICH_API_KEY")
        interval = max(0, _int_env("SCAN_INTERVAL_SECONDS", 0))
        timeout = max(1, _int_env("IMMICH_TIMEOUT_SECONDS", 30))
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    state_dir = Path(os.getenv("STATE_DIR", "/state"))
    client = ImmichClient(url, api_key, timeout_seconds=timeout)

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
