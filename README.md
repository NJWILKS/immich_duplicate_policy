# Immich Duplicate Policy

Conservative policy service for reviewing Immich duplicate groups and identifying safe HEIC/HEIF-over-JPEG candidates.

## v0.1 contract

v0.1 is deliberately read-only. It uses Immich's `GET /api/duplicates` endpoint, evaluates each duplicate group, and writes an audit report. There is no resolve/delete API method in this release and `MODE` is hard-locked to `report`.

A group is marked `SAFE_HEIC_CANDIDATE` only when all of these are true:

- exactly two assets are present;
- exactly one is HEIC/HEIF and one is JPEG;
- MIME type and filename extension do not conflict;
- filename stems match case-insensitively;
- both are image assets;
- dimensions are known and identical;
- capture times are known and within two seconds;
- known camera make/model values do not conflict;
- known GPS coordinates do not conflict by more than 25 metres;
- both assets have the same owner;
- neither asset is a Live Photo, Immich edit, offline, trashed, or part of a stack.

The HEIC/HEIF is the proposed keeper. Immich's own suggested keeper is recorded as evidence but does not drive this policy. Anything that fails a safety check is marked `REVIEW`.

## Configuration

Copy `.env.example` to `.env` and set:

```env
IMMICH_URL=https://photos.example.com
IMMICH_API_KEY=replace-me
MODE=report
SCAN_INTERVAL_SECONDS=3600
```

The API key only needs duplicate read access for v0.1.

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

Each decision contains the duplicate group ID, proposed keeper/trash asset IDs when safe, reason codes for review cases, Immich's suggested keeper IDs, filenames, dimensions, capture-time delta, GPS distance where available, and file sizes where Immich exposes them.

## Development

```bash
python -m pip install -e ".[test]"
pytest
```

CI compiles the package, runs the full test suite, and builds the Docker image.

## Next step

Run v0.1 against the real Immich instance in report mode, inspect actual duplicate groups and decision reasons, then refine the policy before any write-capable release is designed.
