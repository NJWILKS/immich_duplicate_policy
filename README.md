# Immich Duplicate Policy

Conservative policy service for reviewing Immich duplicate groups and automatically resolving only the well-understood HEIC/HEIF-over-JPEG cases.

## v0.3 contract

v0.3 keeps the v0.2 classification policy and adds a one-shot `MODE=apply`.

The long-running Docker service remains `MODE=report`. Apply mode is intended to be run explicitly with `docker compose run --rm -e MODE=apply ...`; it never loops.

Immediately before making any change, apply mode:

1. checks `GET /api/server/features`;
2. refuses to run unless Immich trash is enabled;
3. fetches the live duplicate set again;
4. re-evaluates every group using the current policy;
5. sends only current `SAFE_HEIC_CANDIDATE` groups to Immich's official `POST /api/duplicates/resolve` endpoint.

For each safe group, the HEIC/HEIF is sent as `keepAssetIds` and the JPEG as `trashAssetIds`. Immich therefore performs its normal duplicate-resolution behaviour, including merging supported metadata into the keeper before trashing the duplicate.

Apply mode processes all current safe candidates. Internal batches default to 100 groups and are not a limit on the total run.

If Immich reports a failure for any group, the run records it and exits non-zero. If an API request fails mid-run, processing stops rather than blindly retrying an uncertain mutation.

After execution, the service fetches duplicates again and rewrites `latest.json` from the actual remaining queue.

### Safety boundary

The classifier still requires exactly one HEIC/HEIF plus one JPEG, the same owner, image assets, no MIME/extension conflict, no conflicting known camera identity, and no Live Photo, Immich edit, offline, trashed, or stacked asset.

The three v0.2 evidence-backed relaxations remain:

- **Curator collision slot** — only the curator collision slot may differ in names shaped like `HH-MM-SS-01-Label` vs `HH-MM-SS-02-Label`.
- **Higher-resolution HEIC** — the HEIC may be larger when it is at least as large on both axes and aspect-ratio delta is at most 0.5%.
- **Exact one-hour timezone offset** — capture times may differ by exactly 3600 seconds only when both assets have valid GPS and locations are within 25 metres.

Everything else remains `REVIEW`.

Every safe decision carries a `safe_basis` such as `exact_pair`, `curator_collision_suffix`, `heic_higher_resolution_equivalent`, or `timezone_offset_3600`.

## Configuration

```env
IMMICH_URL=https://photos.example.com
IMMICH_API_KEY=replace-me
MODE=report
SCAN_INTERVAL_SECONDS=3600
IMMICH_TIMEOUT_SECONDS=30
APPLY_BATCH_SIZE=100
```

Report mode only needs duplicate-read access. Apply mode also requires the Immich API-key permissions needed by duplicate resolution and asset deletion.

## Docker

```bash
cp .env.example .env
sudo install -d -o 10001 -g 10001 state
docker compose up -d --build
```

The normal service scans once per hour in report mode. No ports are exposed. The container filesystem is read-only apart from the mounted `/state` directory.

## Execute all safe candidates

Apply is deliberately explicit and one-shot:

```bash
docker compose run --rm -e MODE=apply -e SCAN_INTERVAL_SECONDS=0 immich-duplicate-policy
```

The persistent compose service still remains report-only after that command exits.

Apply refuses to run if Immich trash is disabled because Immich's duplicate resolver permanently deletes trash candidates when the server trash feature is off.

## Reports and audit

Report mode writes:

- `state/latest.json` — current duplicate snapshot and summary;
- `state/decisions.jsonl` — append-only classification history.

Apply mode additionally writes:

- `state/last_apply.json` — complete latest execution summary and per-group results;
- `state/apply_actions.jsonl` — append-only execution audit.

After apply finishes, `latest.json` is regenerated from Immich so it describes the remaining duplicate queue.

## Development

```bash
python -m pip install -e ".[test]"
pytest
```

CI compiles the package, runs the full test suite, and builds the Docker image.
