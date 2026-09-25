# Immich Duplicate Policy

Conservative policy service for reviewing Immich duplicate groups and identifying safe HEIC/HEIF-over-JPEG candidates.

## v0.2 contract

v0.2 is still deliberately read-only. It uses Immich's `GET /api/duplicates` endpoint, evaluates each duplicate group, and writes an audit report. There is no resolve/delete API method in this release and `MODE` remains hard-locked to `report`.

A group is marked `SAFE_HEIC_CANDIDATE` only when it is exactly one HEIC/HEIF plus one JPEG, both belong to the same owner, both are images, MIME type and filename extension do not conflict, known camera identity does not conflict, and neither asset is a Live Photo, Immich edit, offline, trashed, or part of a stack.

v0.2 allows three narrowly-scoped, evidence-backed relaxations:

- **Curator collision slot** — filenames may differ only in the curator collision slot in names shaped like `HH-MM-SS-01-Label` vs `HH-MM-SS-02-Label`; changes to the clock or label still require review.
- **Higher-resolution HEIC** — dimensions may differ only when the HEIC is at least as large on both axes, larger on at least one axis, and the aspect-ratio delta is at most 0.5%.
- **Exact one-hour timezone offset** — capture times may differ by exactly 3600 seconds only when both assets have valid GPS and the recorded locations are within the existing 25 metre GPS tolerance.

Normal capture-time tolerance remains two seconds. Missing dimensions or capture time still require review.

The HEIC/HEIF is always the proposed keeper for safe groups. Immich's own suggested keeper is recorded as evidence but does not drive the policy.

Every safe decision includes a `safe_basis` list so combined relaxations remain auditable. Examples are `exact_pair`, `curator_collision_suffix`, `heic_higher_resolution_equivalent`, and `timezone_offset_3600`.

Everything else remains `REVIEW`. In particular, v0.2 does not automatically resolve Live Photos, multi-asset groups, JPEG/JPEG groups, videos, ambiguous filename changes, arbitrary timestamp differences, or genuinely conflicting image evidence.

## Configuration

Copy `.env.example` to `.env` and set:

```env
IMMICH_URL=https://photos.example.com
IMMICH_API_KEY=replace-me
MODE=report
SCAN_INTERVAL_SECONDS=3600
```

The API key only needs duplicate read access for v0.2.

## Docker

```bash
cp .env.example .env
sudo install -d -o 10001 -g 10001 state
docker compose up -d --build
```

The default compose configuration scans once per hour. Set `SCAN_INTERVAL_SECONDS=0` to run once and exit.

No ports are exposed. The container filesystem is read-only apart from the mounted `/state` directory. The image runs as UID/GID `10001:10001`, so the host `state/` directory must be writable by that identity.

## Reports

Two files are written under `state/`:

- `latest.json` — complete latest scan snapshot;
- `decisions.jsonl` — append-only audit history.

Each decision contains the duplicate group ID, proposed keeper/trash asset IDs when safe, review reason codes, Immich's suggested keeper IDs, filenames, dimensions, capture-time delta, GPS distance where available, file sizes, and compact per-asset state.

`latest.json` also contains a summary with:

- decision counts;
- counts for each safe basis;
- counts for each remaining review reason.

The intent is not to eliminate every manual decision. The service removes the well-understood, repetitive cases and leaves a smaller, clearly classified queue for human review.

## Development

```bash
python -m pip install -e ".[test]"
pytest
```

CI compiles the package, runs the full test suite, and builds the Docker image.

## Next step

Run v0.2 against the real Immich instance in report mode and confirm the expected safe/review population before designing any write-capable release.
