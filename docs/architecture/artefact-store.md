# L3: artefact store

Where heavy originals and intermediates live, how the storage tiers relate, and how they are backed up. Source: XADR-SCITADEL-008 §12 (artefact store, raw retention) and §8 (staged infrastructure: tiers and backup). The store's trait is `ArtefactStore` ([DES-013](tessera-boundary.md)) and every byte's path on the stage-0 layout is [DES-021](adapters-and-pool.md); this file adds the tier model and the backup path.

> **Source legend.** As in [the tessera boundary](tessera-boundary.md). **Tiers at stage 0** (owner, 2026-11-18, SYS-015): the hot working set on the KC3000 NVMe (LUKS, btrfs; not ZFS), the warm tier of 20+ TB of HDD attached to anvil behind the `gerchowl/g-fleet#1363` versitygw/ZFS store, and the cold mirror on a Hetzner Storage Box. Hot and warm share anvil as one failure domain. Every DES below is `proposed`.

| DES | Title | Realises | Uses |
|---|---|---|---|
| DES-041 | Storage tiers, keep-everything retention and stage migration | SYS-011, SYS-012, SYS-013, SYS-014, SYS-015, SYS-017 | DES-013, DES-021 |
| DES-042 | Snapshots, cold mirror and restore | SYS-016, SYS-045, SYS-046, SYS-047, SYS-072 | DES-012, DES-014, DES-041 |

## 1. Tiers, retention and stage migration (DES-041)

| Tier | Holds | Notes |
|---|---|---|
| Hot | the POSIX working copy, indexes, GPU exchange, ledgers | local NVMe only for BM25 and ANN random access (SYS-012); a rebuildable mirror of the buckets |
| Warm | raw inputs, cascade outputs T1 to T4, canonical sealed products and their history | S3-compatible; bulk, sequential-friendly; scrubs and snapshots (SYS-015) |
| Cold | the encrypted mirror of warm and of the non-rebuildable buckets | the only copy outside anvil (DES-042, section 2) |

- **Heavy originals stay out of the corpus database.** PDFs and raw JATS, TEI, HTML or XML are content-addressed objects keyed by blake3; `works` rows reference them by hash and source URL; raw XML never goes into a product ([DES-013](tessera-boundary.md)).
- **Keep everything** (owner, 2026-11-11): every raw input and every cascade tier's intermediate, each keyed by blake3 with its provenance, so a re-extraction starts from stored OCR and nothing depends on upstream availability (SYS-014).

| Raw input or output | Lives in | Notes |
|---|---|---|
| Open-access PDF | warm, mirrored cold | blake3, URL and fetch date; a re-fetch is verified against the hash |
| Paywalled, acquired PDF | warm, mirrored cold | licence-gated; disabled in phase 1 |
| JATS, TEI, USPTO XML, bulk snapshots | warm, zstd, mirrored cold | |
| Cascade outputs T1 to T4 | warm, mirrored cold | keyed by input hash, tool, model, version |

- **Before the warm tier exists** the same set is kept on the KC3000 within an explicit quota; at the quota, ingest **pauses with an alert** and deletes nothing. The only class an operator may drop by hand is a re-fetchable open-access PDF whose hash is recorded (`RawDrop`). Nothing is deleted automatically (SYS-014, [DES-021](adapters-and-pool.md)).
- **Object tiers per project** are buckets with their own credentials and roles (SYS-013); retention expiry is a role, never an ad-hoc delete (SYS-017).
- **Stage migration** (stage 1: Hetzner serving and object storage; stage 2: hosted spaces; on-prem) changes configuration, not formats or code: the `ArtefactStore` and `GenerationCatalog` backends are chosen at the composition root ([DES-001](tessera-boundary.md), SYS-039). The cutover to a new warm store does not flip the endpoint until a restore from cold of the migrated set has passed (SYS-072).
- **Disk budget** and the capacity model are in [L2 infrastructure](../vmodel/L2-infrastructure.md), not copied here.

## 2. Snapshots, cold mirror and restore (DES-042)

- **Snapshots.** btrfs subvolumes are snapshotted read-only: `state` hourly, `keep` and `research` daily, derived subvolumes minimally (SYS-045).
- **Off-box backup.** The non-rebuildable data (`keep`, `research`, state dumps) is backed up client-side encrypted with `restic` to the Storage Box; keys only in the fleet's sops; research data additionally goes to the separate fleet's target (SYS-046, SYS-016).
- **The mirror gates ingest.** Because hot and warm are one failure domain, no run that writes raw inputs starts until the first backup has completed and a restore from cold has passed, and none starts while the newest backup is older than 48 h; that pauses with an alert and deletes nothing (SYS-072, gate 1 of [DES-020](adapters-and-pool.md)).
- **Restore from an empty host** brings back `keep` objects first and verifies each object's blake3 against the ledger, then the ledger, then the catalog pointers; it runs only through `hub restore`, which opens a restore epoch and holds base permits and paid search until its checks pass ([DES-059](tessera-boundary.md), SYS-047, [C-007 ruling](https://github.com/nerdmachines/scitadel-hub/issues/27#issuecomment-6995801449)).
- **Owner actions** (g-fleet issues, not hub code): `gerchowl/g-fleet#1363`, `gerchowl/g-fleet#1438`, `gerchowl/g-fleet#1263` and `gerchowl/g-fleet#1649`.

## 3. Verification

| Test | Verifies | Method | Pass criterion |
|---|---|---|---|
| TEST-135 | DES-041 | A fixture ingest into a scratch store with a tiny quota, a stage-0 to a second `ArtefactStore` backend swap, and an operator `RawDrop` | at the quota, ingest pauses with an alert and 0 objects are deleted; only a re-fetchable OA PDF with a recorded hash can be dropped; the backend swap changes no caller; 0 XML in any product |
| TEST-136 | DES-042 | A scratch host with the hourly and daily schedules, a restic run to a test repository, a backup 49 h old, and a restore onto an empty volume | 0 plaintext objects in the repository; no raw-writing run starts at 49 h; every restored object matches its ledger blake3; `restic check` passes |
