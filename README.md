# Immich Duplicate Policy

Conservative policy service for reviewing Immich duplicate groups.

## First release

The initial release is deliberately read-only. It will:

- read duplicate groups from the Immich API;
- identify narrowly-defined HEIC/HEIF versus JPEG pairs;
- prefer the HEIC/HEIF only when safety checks agree;
- classify everything else for review;
- emit an auditable JSON decision record;
- never delete or modify Immich assets.

Write support will be added only after real read-only decisions have been reviewed.
