# L2: infrastructure

How the system requirements of [L2](L2-system-requirements.md) are met on hardware: stage 0 on anvil's KC3000 in enough detail to apply as written, then stages 1 and 2 and on-prem as shorter sketches tied to the staged text of the decision record. Every claim about a system requirement cites its `SYS` node; every test is in the [verification plan](L2-verification-plan.md).

> **Source legend.** `XADR-SCITADEL-008` is the vig-os/scitadel decision record "scitadel-hub: a lab corpus server" (ADR 008, status Proposed, [pull request 317](https://github.com/vig-os/scitadel/pull/317)); `§N` is a section of it. `gerchowl/g-fleet#N` is an issue of the private fleet repository, written in code style because it cannot be linked from this public repository. A figure marked *(estimate)* is a first value to be calibrated by the first measurement. This document specifies no commercial figures.

## 1. Facts the layout rests on

Read-only probes of anvil on 2026-11-09 (`lsblk`, `findmnt`, `df`, `btrfs filesystem usage`, `btrfs subvolume list`, `btrfs qgroup show`), plus the g-fleet module that owns the pool (`modules/anvil-vm-pool.nix`).

| Fact | Value | Consequence |
|---|---|---|
| The KC3000 | 4 TB (3.73 TiB), on the chipset at PCIe Gen4 x4, LUKS2, then btrfs (`-d single -m dup`, label `anvil-vm`), mapped as `/dev/mapper/anvil-vm` | **Not ZFS.** Never design against a ZFS pool on anvil. ZFS exists only in the future storage host (`gerchowl/g-fleet#1363`). |
| Mount | `/var/lib/microvms`, the pool's top level (`subvolid=5`), options `noatime,compress=zstd:1,ssd,discard=async,space_cache=v2` | Compression is pool-wide (zstd level 1). A subvolume can switch it off but cannot pick another level. |
| Space | about 1.0 TiB used, about 2.7 TiB free (`df` shows 2.8 T; the issue's "about 2.9 TB" in decimal units) | The hub budget below is sized against this. |
| Existing content | `vm-dev` and `vm-runner` directories with raw ext4 images (vm-dev `home.img` 768 GiB, `nix-rw.img` 512 GiB, both sparse), logs. **No subvolumes** below the top level; **quotas not enabled** | Everything below is new. Quotas have to be switched on first. |
| Kernel and tools | Linux 7.2.9, btrfs-progs 7.1 | Simple quotas (squota) are available. |
| Who else uses the pool | The g-fleet pool module watches fill at 80 % and 90 % and checks guest image budgets at boot (`storage-budget-sizematch`); `vm-storage` (versitygw) is to run on it (`gerchowl/g-fleet#1449`) and was **not deployed** on the probe date | The hub budget must be registered with that module (owner action O-4), and the bucket path is `#1449`'s to confirm (O-6). |
| `/srv/anvil` | On the **990 PRO** (`/home`, `/srv`, 76 % used, 458 GB free), **not** on the KC3000 | XADR-SCITADEL-008 §8 says the KC3000 holds the working copy "under `/srv/anvil/projects/<project>/`". That path is only reachable by a bind mount from the KC3000 (section 3). |

## 2. Stage 0: the layout on the KC3000

Two roots, both new, both plain directories created by root:

- `HUB=/var/lib/microvms/data/scitadel-hub` holds the hub's own subvolumes.
- `GW=/var/lib/microvms/data/s3` is the proposed POSIX backend root of the vm-storage gateway; the four hub buckets are subvolumes inside it. **The path is a proposal; `gerchowl/g-fleet#1449` fixes it** (owner action O-6). The apply script takes it as one variable.

The `data/` directory keeps project data apart from the microVM directories that microvm.nix manages directly under `/var/lib/microvms/`.

### 2.1 Subvolumes

Quotas are hard limits in GiB on the subvolume's qgroup. They sum to 1,530 GiB, which is about 1.5 TiB and 55 % of the 2.7 TiB free *(estimate)*, and leaves about 1.2 TiB for the microVM images and for growth. SYS-011 pins the sum (≤ 1,536 GiB) and the alert thresholds.

| Subvolume | Path | Holds | Attributes | Quota (GiB) | Snapshots |
|---|---|---|---|---|---|
| `products` | `$HUB/products` | sealed `.tsra` products: base, deltas, `current`; embeddings; graph edge tables. The hot, rebuildable working copy | COW, `chattr +m` (no compression) | 400 | daily, keep 3 days |
| `index` | `$HUB/index` | BM25 (tantivy) and ANN indexes, graph adjacency caches | COW, `chattr +m` | 350 | none (rebuildable) |
| `staging` | `$HUB/staging` | adapter pool and cache, in-flight downloads, internal Parquet staging | COW, pool default zstd level 1 | 150 | none |
| `state` | `$HUB/state` | SQLite databases and ledgers (subscriptions, credit ledger, freshness, job and hash ledger, retention audit) | **`chattr +C` (nodatacow)** | 20 | hourly, keep 48 h, 14 d, 8 w |
| `gpu-io` | `$HUB/gpu-io` | `in/`, `out/<run-id>/`, `models/` for GPU jobs | COW, `chattr +m` | 100 | none |
| `scitadel-hub-scratch` | `$GW/scitadel-hub-scratch` | bucket, 48 h | COW, pool default | 50 | none |
| `scitadel-hub-runs` | `$GW/scitadel-hub-runs` | bucket, 28 d | COW, pool default | 100 | none |
| `scitadel-hub-keep` | `$GW/scitadel-hub-keep` | bucket, no expiry | COW, pool default | 340 | daily, keep 14 days and 4 weeks |
| `scitadel-hub-research` | `$GW/scitadel-hub-research` | bucket, versioned, write-once when finished | COW, pool default | 20 | daily, keep 14 days, 8 weeks and 12 months |

Why these attributes:

- **No compression (`+m`) on `products`, `index` and `gpu-io`.** Sealed products already carry zstd inside Vortex, embeddings are floating-point vectors, and index files are read by memory-mapped random access: a compressed btrfs extent is up to 128 KiB, so a 4 KiB random read would decompress up to 32 times what it needs. SYS-012 measures the result.
- **Copy-on-write stays on for the indexes.** Tantivy segments and the ANN and adjacency caches are written once and never modified in place (XADR-SCITADEL-008 §4: unsealed, rebuildable, stamped with a seal). `nodatacow` would buy nothing for them and would cost checksums, so silent bit rot would go unseen, and cheap snapshots. The rule used here: **`nodatacow` only where a file is rewritten in place.**
- **`nodatacow` on `state` only.** SQLite with a write-ahead log rewrites pages in place; on copy-on-write that fragments. Hourly snapshots make the first write after each snapshot copy-on-write anyway, so fragmentation is reduced, not removed; that is acceptable for a volume that is small (20 GiB), loses checksums, and is protected by a nightly `PRAGMA integrity_check`, a `.backup` dump into `scitadel-hub-keep`, and the hourly snapshots. The attribute must be set while the subvolume is empty; it applies only to files created afterwards.
- **Any later file that is rewritten in place** (an ANN cache that the L3 design updates in place, for example) goes to a dedicated small `+C` subvolume, never to `index`.
- **Quota mode.** Simple quotas (`btrfs quota enable --simple`): low overhead on a pool that holds 800 GiB-class images and will hold many snapshots. In this mode an extent is charged to the subvolume that created it, so data pinned by a snapshot still counts against its owner until the snapshot expires. Retention deletes therefore free space only after the snapshots covering them age out; the quotas above leave room for that.
- **Pool-wide guard.** Alerts at 80 % and 90 % of any quota and below 500 GiB of pool free space (SYS-044). Above 90 % of the pool the ingest scheduler stops submitting work and reports (a stop, never an eviction).

### 2.2 Applying it

Owner action O-2, run as root on anvil. It is safe to re-run (the free-space check applies to the first run only, and a path that exists but is not a subvolume aborts it). For existing subvolumes limits and ownership are re-applied and `+C` affects only files created afterwards. Run it **before** the hub microVM first boots, because microvm.nix's tmpfiles rules create a missing share source as a plain directory, which would defeat the subvolume.

```bash
#!/usr/bin/env bash
# scitadel-hub stage-0 data layout on the KC3000 pool (anvil-vm). Run as root on anvil.
set -euo pipefail

POOL=/var/lib/microvms
HUB="${POOL}/data/scitadel-hub"
GW="${GW:-${POOL}/data/s3}"          # g-fleet#1449 fixes this path (O-6)
GW_OWNER="${GW_OWNER:-microvm:kvm}"  # the gateway's identity is g-fleet#1449's call
GIB=$((1024 * 1024 * 1024))
BUDGET_GIB=1530
GUARD_GIB=500

# 1. right pool, enough room
[[ "$(findmnt -n -o SOURCE,FSTYPE "${POOL}")" == "/dev/mapper/anvil-vm btrfs" ]] \
  || { echo "refusing: ${POOL} is not the anvil-vm btrfs pool" >&2; exit 1; }
if [[ ! -d "${HUB}" ]]; then   # first run only: later runs hold hub data already
  free_bytes="$(df -B1 --output=avail "${POOL}" | tail -n 1 | tr -d ' ')"
  (( free_bytes > (BUDGET_GIB + GUARD_GIB) * GIB )) \
    || { echo "refusing: pool free space is below budget plus guard" >&2; exit 1; }
fi

# 2. simple quotas, once
btrfs qgroup show "${POOL}" >/dev/null 2>&1 || btrfs quota enable --simple "${POOL}"

# 3. directories (plain)
install -d -m 0755 "${POOL}/data" "${HUB}" "${GW}"

# 4. subvolume helper: path, limit in GiB, attribute (m, C or -), owner, mode
mk() {
  local path="${1}" limit="${2}" attr="${3}" owner="${4}" mode="${5}"
  if [[ -e "${path}" ]]; then
    btrfs subvolume show "${path}" >/dev/null 2>&1 \
      || { echo "refusing: ${path} exists but is not a subvolume" >&2; exit 1; }
  else
    btrfs subvolume create "${path}"
  fi
  case "${attr}" in
    m) chattr +m "${path}" ;;
    C) chattr +C "${path}" ;;   # only effective for files created after this point
  esac
  chown "${owner}" "${path}"
  chmod "${mode}" "${path}"
  btrfs qgroup limit "${limit}G" "${path}"
}

mk "${HUB}/products"  400 m microvm:kvm      0750
mk "${HUB}/index"     350 m microvm:kvm      0750
mk "${HUB}/staging"   150 - microvm:kvm      0750
mk "${HUB}/state"      20 C microvm:kvm      0750
mk "${HUB}/gpu-io"    100 m larsgerchow:users 2775   # owned by the job user, group users, setgid
mk "${GW}/scitadel-hub-scratch"   50 - "${GW_OWNER}" 0750
mk "${GW}/scitadel-hub-runs"     100 - "${GW_OWNER}" 0750
mk "${GW}/scitadel-hub-keep"     340 - "${GW_OWNER}" 0750
mk "${GW}/scitadel-hub-research"  20 - "${GW_OWNER}" 0750

# 5. gpu-io skeleton, and the mount point for the bind mount of section 4
install -d -o larsgerchow -g users -m 2775 "${HUB}/gpu-io/in" "${HUB}/gpu-io/out" "${HUB}/gpu-io/models"
install -d -o larsgerchow -g users -m 2775 /srv/anvil/projects/scitadel-hub   # a NEW project directory
chattr +i /srv/anvil/projects/scitadel-hub   # an unmounted mount point must not accept job writes (bind mount is nofail)

# 6. report
btrfs subvolume list -t "${POOL}"
btrfs qgroup show -re "${POOL}"
lsattr -d "${HUB}"/* "${GW}"/scitadel-hub-*
```

After the script, these checks must hold (they are the manual drill of SYS-011): `btrfs qgroup show` lists nine limits that sum to 1,530 GiB; `lsattr` shows `m` on `products`, `index` and `gpu-io` and `C` on `state`; `df` on the pool still shows at least 500 GiB free; writing past a limit on a scratch file returns `EDQUOT`.

Ownership of the five hub-side subvolumes is `microvm:kvm`, like the share sources of vm-dev. How the guest's service user maps onto that is a detail of the NixOS module (`nerdmachines/scitadel-hub-deploy#2`), not of this layout.

### 2.3 Snapshots

btrbk (the pool is "btrbk / snapper compatible" in the host's own notes) takes read-only snapshots into `${POOL}/data/.snapshots/<subvolume>.<UTC stamp>`, a plain directory beside the hub root. Retention is as in the table above. `${POOL}/data/.snapshots` is created by the same owner action (O-3). The policy is exercised by SYS-045.

## 3. Access paths

```text
anvil host (admin plane)
  /var/lib/microvms/data/scitadel-hub/{products,index,staging,state,gpu-io}    btrfs subvolumes, KC3000
  /var/lib/microvms/data/s3/scitadel-hub-{scratch,runs,keep,research}          gateway backend root
  /srv/anvil/projects/scitadel-hub  <-- bind mount of .../gpu-io               (project path of gpu_submit)

vm-hub microVM (stage-0 hub, "tenant zero")            vm-storage microVM (versitygw)
  virtiofs: products  -> /var/lib/scitadel-hub/products      serves the four buckets from GW
  virtiofs: index     -> /var/lib/scitadel-hub/index         over S3 on the microVM bridge
  virtiofs: staging   -> /var/lib/scitadel-hub/staging
  virtiofs: state     -> /var/lib/scitadel-hub/state
  virtiofs: gpu-io    -> /var/lib/scitadel-hub/gpu-io
  S3 client  ----------------------------------------->  scitadel-hub-{scratch,runs,keep,research}
```

| Consumer | Path | Mechanism | Rights |
|---|---|---|---|
| Hub service in `vm-hub` | `/var/lib/scitadel-hub/{products,index,staging,state,gpu-io}` | **one virtiofs share per subvolume**, never the parent directory (a share that crosses into a nested subvolume presents a second device, and every subvolume root has the same inode number). The one exception is the gateway's share of `$GW`, whose buckets are nested subvolumes: O-6 must verify the inode behaviour there, or share the four buckets separately | read-write |
| Hub service, object tiers | the four `scitadel-hub-*` buckets | S3 over the microVM bridge to vm-storage, with the hub's own gateway account, credentials from the hub's `sops` file | per role (section 4) |
| GPU jobs (`gpu_submit`) | `/srv/anvil/projects/scitadel-hub/{in,models,out/<run-id>}` | bind mount of `gpu-io` onto the project path; jobs run as `bash -lc` with cwd `/` and `cd` there themselves (`docs/gpu-jobs.md`) | read `in/` and `models/`; write only a **new** `out/<run-id>/` and `$GPU_JOB_OUT` |
| `vm-dev` | `/srv/anvil/projects/scitadel-hub` through the existing `anvil-projects` virtiofs share, if the bind mount propagates (to verify) | existing share | not a consumer; light inspection only. Note `gerchowl/g-fleet#1402`: `/srv/anvil` is exported read-write into vm-dev, so `gpu-io` is modifiable by any agent there. It holds derived, rebuildable data, and the hub's hash ledger (SYS-049) rejects anything it did not expect |
| Tenant-simulation microVMs | their own subvolumes under `${POOL}/data/scitadel-hub-sim/<tenant>/` with their own gateway accounts | virtiofs per subvolume | simulated tenants and a tiny fixture corpus only; never the hub's production subvolumes (`gerchowl/g-fleet#1474`, rule 3) |
| Operator and restore | the subvolumes on the host | root | read; restores follow SYS-047 |

The `vm-hub` shares, as microvm.nix `shares` entries (the hub module in `nerdmachines/scitadel-hub-deploy` owns the real definition, which g-fleet imports without patching):

```nix
microvm.shares = map (name: {
  proto = "virtiofs";
  tag = "hub-${name}";
  source = "/var/lib/microvms/data/scitadel-hub/${name}";
  mountPoint = "/var/lib/scitadel-hub/${name}";
}) [ "products" "index" "staging" "state" "gpu-io" ];
```

The bind mount, host side (owner action O-5):

```nix
fileSystems."/srv/anvil/projects/scitadel-hub" = {
  device = "/var/lib/microvms/data/scitadel-hub/gpu-io";
  options = [ "bind" "nofail" "x-systemd.requires-mounts-for=/var/lib/microvms" ];
};
```

**Rules that follow from the fleet's own rules.**

- GPU jobs never receive S3 credentials in stage 0: the hub stages inputs into `in/` and promotes validated outputs from `out/<run-id>/` into `products`. Per-workload short-lived credentials (`gerchowl/g-fleet#1449`) may later let a job write its output straight to `scitadel-hub-runs`.
- A job writes **only new files** under `out/<run-id>/`. The fleet's add-only rule for `/srv/anvil` (existing data is never moved, rewritten or deleted, the project's own included) is respected by construction. Cleaning old `out/` directories needs an exception to that rule: owner action O-8, settled in `gerchowl/g-fleet#1363` (H6) as XADR-SCITADEL-008 §2 says. Until then nothing is deleted, the 100 GiB quota alerts at 80 %, and the ingest scheduler stops submitting at 90 %.
- Every submission declares VRAM, runs at low priority, is chunked to the default 30-minute runtime with checkpoints under `out/<run-id>/` (SYS-048), and backfills or re-embedding sweeps never run here (SYS-051).
- Serving holds no GPU device (SYS-024).

**Decision gate G-2 (random-read latency through virtiofs).** The indexes are read by memory-mapped random access, and a guest reads them through virtiofs. SYS-012 measures p95 4 KiB random read through that path. If it exceeds 1 ms *(estimate)*, the `index` subvolume is not shared but holds a sparse raw ext4 image attached to `vm-hub` as a virtio block device, the way vm-dev's images are attached; the quota then caps the image file. The gate is decided by the measurement, not by preference, and the rest of the layout is unaffected.

## 4. Buckets (g-fleet#1449 tiers)

`gerchowl/g-fleet#1449` (owner go 2026-11-09) provides, per project, `<project>-scratch` (48 h), `<project>-runs` (28 d, a warning at 72 h or less remaining), `<project>-keep` (no expiry) and `<project>-research` (indefinite, versioned, write-once when finished). For the project `scitadel-hub`:

| Bucket | Tier meaning | What the hub puts there |
|---|---|---|
| `scitadel-hub-scratch` | 48 h | cascade hand-off payloads between ingest stages; quarantined inputs awaiting triage; tenant-simulation staging |
| `scitadel-hub-runs` | 28 d | run manifests, QC and golden-set diff reports, embedding-drift reports, candidate delta products before promotion, copies of job logs |
| `scitadel-hub-keep` | no expiry; deleted only by the retention role | **canonical sealed products** (`base/<release>/`, `delta/<date>.tsra`, `current`), the **content-addressed artefact store** (blake3 keys: kept TEI and JATS, paywalled originals when that gate opens), the private golden fixtures (the non-CC fixture bucket of XADR-SCITADEL-008 §13), nightly `state` dumps |
| `scitadel-hub-research` | versioned, write-once when finished | finished evaluation results only: grounding-benchmark runs on a pinned release, golden-set baselines |

**Why the corpus is in `keep`, not `research`.** XADR-SCITADEL-008 §2 retires generations by an explicit retention policy (the last two bases and their deltas), while `research` is write-once and indefinite. The two rules meet in `gerchowl/g-fleet#1363` (H6), per the same section. Until that is settled the corpus generations live in `keep`, where one dedicated role may delete a retired generation by policy and nothing else may delete at all (SYS-017). `research` holds only data that is meant to be immutable.

**Roles (gateway accounts and permissions).** Each cell is what the role may do; "create" means a new key and never an overwrite.

| Role | scratch | runs | keep | research |
|---|---|---|---|---|
| hub serving | none | read | read | read |
| hub ingest and promotion | read, write | read, write | create; overwrite **only** the `current` pointer key | create once |
| hub retention (the only deleter) | none | none | delete keys of a retired generation | none |
| GPU job (later, short-lived credentials) | read, write | create | none | none |
| backup agent (restic) | none | none | read | read |
| tenant-simulation account | own buckets only | own buckets only | own buckets only | own buckets only |

No role, and no project, can overwrite a finished `research` object or read another project's bucket (SYS-013). Two points are for `#1449` to verify at the pinned versitygw source, as that issue already asks: that a pre-created subvolume directory is adopted as a bucket (otherwise the provisioner creates buckets as subvolumes instead of `mkdir`), that a per-key rule or versioning lets the ingest role move only `current`, and where the gateway keeps object versions (a separate versioning directory would escape the `research` quota, its snapshots and the backup set). If a per-key rule is missing, `current` becomes a sequence of pointer objects with the newest winning, which needs no overwrite.

## 5. Where each kind of data goes

| Data | Location (stage 0) | Why there | Rebuildable | Backed up |
|---|---|---|---|---|
| Adapter pool (raw bulk files per source: PatentsView tables, weekly grant XML, OpenAlex snapshot parts) | `staging/adapters/<source>/pool/` | compressible text; re-fetchable; deleted after a successful seal, a re-fetch is verified by hash | yes, from upstream | no |
| Adapter cache (conditional-request responses, pacing state) | `staging/adapters/<source>/cache/` | small, many files; pacing and credit ledgers themselves live in `state` | yes | no |
| In-flight downloads (open-access PDFs, XML) | `staging/downloads/` | PDFs are deleted after ingest (SYS-014) | yes | no |
| Internal Parquet staging, until tessera#778 lands | `staging/parquet/` | never published (XADR-SCITADEL-008 §2) | yes | no |
| Raw originals worth keeping (TEI, JATS) | `scitadel-hub-keep`, artefact store | content-addressed, never in a product, hub never serves PDF bytes (D-007) | cost of re-fetch | yes |
| `.tsra` products, hot working copy | `products/<collection>/base|delta/…`, `current` | read locally by the query engine | yes, from `keep` | via `keep` |
| `.tsra` products, canonical copy | `scitadel-hub-keep` (stage 0), then the warm tier | the S3 store of record; the hot copy is a mirror of it | yes | yes |
| Embeddings (one product per model, beside each shard) | `products/…/embeddings/<model>/` | native Vortex fixed-size lists; about 12 GB for patents and about 51 GB for 50,000,000 chunks at 512 dimensions in fp16 *(estimates)* | yes (GPU cost) | via `keep` |
| BM25 and ANN indexes | `index/bm25/…`, `index/ann/…` | **local NVMe random access**, uncompressed, copy-on-write (SYS-012) | yes, ≤ 24 h *(estimate)* (SYS-021) | no |
| Graph: typed edge tables | `products/…/graph/` | tables are products | yes | via `keep` |
| Graph: adjacency (CSR) cache | `index/graph/` | derived cache | yes | no |
| Hub state: subscriptions, credit and freshness ledgers, job and hash ledger, retention audit, metering counters | `state/` (SQLite, `+C`) | small, rewritten in place | partly (ledgers are not) | yes: hourly snapshots, nightly dump to `keep` |
| GPU inputs, outputs, model weights | `gpu-io/{in,out,models}` | visible to `gpu_submit` at the project path; weights fetched at first run through a signed manifest, never baked into an image (SYS-056) | yes | no |
| Run records, QC and diff reports | `scitadel-hub-runs` | 28-day working record | yes | no |
| Finished benchmark results | `scitadel-hub-research` | immutable by tier | no | yes |
| Secrets | the hub's own `sops` file, `/run/secrets` in the guest | never on any volume above (SYS-040) | n/a | in the fleet's secrets backup |

The hot copy and the canonical copy of a sealed product are two separate byte copies on the same disk until the warm tier exists; the quotas above account for both.

## 6. Durability

In order of when each layer exists.

1. **Snapshots (btrfs, stage 0 now)**, SYS-045. They protect against accidental deletion and overwrite. They do **not** protect against loss of the KC3000, of anvil or of the LUKS key: a snapshot shares the disk with its source.
2. **Off-box encrypted backup (restic to a Hetzner Storage Box)**, SYS-046, SYS-016. Nightly, client-side encrypted, keys only in the fleet's `sops`. The backup set is exactly the non-rebuildable data: `scitadel-hub-keep`, `scitadel-hub-research` and the `state` dumps. Retention in the repository: 14 daily, 8 weekly, 12 monthly. A monthly `restic check --read-data-subset=5%`. The Storage Box does not accept `zfs receive`, which is why this layer is restic (or borg) and not block replication. It can start **before** the storage host exists, because it needs no ZFS (owner action O-9).
3. **Interim target (`gerchowl/g-fleet#1438`).** The fleet's decided interim backup is the vm-storage S3 on this same KC3000, separate from the 990 PRO. For hub data that already lives on the KC3000 it adds no failure domain, so it is not counted here. Research data follows the owner's refinement of `#1438`: a client-side-encrypted push to the separate fleet's target, with a restore drill and `restic check` before any research cutover.
4. **Replication to the storage host (`gerchowl/g-fleet#1363`), once it exists.** The canonical bucket contents move to the warm S3 box by a checksum-verified copy (`rclone copy --checksum`, then a listing and hash compare that must show 0 differences, SYS-015), the hub's S3 endpoint is flipped by configuration, and the KC3000 buckets shrink to the hot working set. The box then snapshots with sanoid and ships off-site with restic to the Storage Box (the same layer 2, now sourced from the warm box).
5. **Restore drill, quarterly and before any keep or research cutover**, SYS-047: an empty microVM, the backup set, rebuilt indexes, the smoke suite and the golden queries, within 8 h *(estimate)* (OUT-017).

**What is and is not at risk before layer 2 exists.** Until the first off-box backup runs, hub data has a single failure domain. In phase 1 almost all of it is rebuildable from public upstreams. What is not: the content-API TEI (paid per fetch), the private golden fixtures, finished research results and the `state` ledgers. Until layer 2 and its first successful restore drill exist, those four are the reason not to cut over `keep` or `research` for real use (the gate of `#1438`).

## 7. Owner actions

Nothing here has been filed or changed. Each item names the g-fleet issue that owns it; "to file" gives a proposed title.

| # | Action | Owner issue |
|---|---|---|
| O-1 | Decide whether stage-0 retention on the KC3000 is 1 base and its deltas (proposed here, in SYS-017) rather than the default 2, until the warm tier exists. The quotas hold one base. | `gerchowl/g-fleet#1363` |
| O-2 | Enable simple quotas on the `anvil-vm` pool and apply the layout script of section 2.2 (subvolumes, attributes, limits) before the hub microVM first boots. | to file: "anvil: scitadel-hub stage-0 data subvolumes and quotas on the KC3000 pool" (related `#1474`) |
| O-3 | Install the btrbk policy of section 2.3 for the hub subvolumes. | to file: "anvil: btrbk snapshot schedule for the scitadel-hub subvolumes" (related `#1438`) |
| O-4 | Register the hub budget (1,530 GiB, nine limits) with the pool's fill watchdog and budget check. | to file: "anvil-vm pool: register the scitadel-hub subvolume budget with the fill watchdog" (module `anvil-vm-pool.nix`) |
| O-5 | Add the bind mount of `gpu-io` at `/srv/anvil/projects/scitadel-hub` and check that `vm-dev` sees it through `anvil-projects`. | to file: "anvil: bind the scitadel-hub gpu-io subvolume at /srv/anvil/projects/scitadel-hub" (related `#1402`) |
| O-6 | Provision `scitadel-hub-{scratch,runs,keep,research}` per tier. Fix the gateway root (proposed `/var/lib/microvms/data/s3`), make each hub bucket a btrfs subvolume (or adopt the pre-created ones), and verify per-key rules or versioning for the `current` pointer. | `gerchowl/g-fleet#1449` (depends on `#1377` for vm-storage's RAM slot) |
| O-7 | Define `vm-hub` (the hub as a microVM) with the five virtiofs shares of section 3, importing the private module without patching it; hub secrets in their own `sops` file. | `gerchowl/g-fleet#1474` (blocked on `nerdmachines/scitadel-hub-deploy#2`) |
| O-8 | Settle how the add-only rule for `/srv/anvil` meets hub retention of old `out/` directories and of `research` versus corpus generations. | `gerchowl/g-fleet#1363` (H6 per XADR-SCITADEL-008 §2) |
| O-9 | Provision the Hetzner Storage Box and the restic repository, keys only in `sops`, nightly job and monthly check, before the storage host exists. | to file: "backup: restic of scitadel-hub keep and research to the Hetzner Storage Box" (related `#1263`, `#1363`) |
| O-10 | Interim backup target and the restore drill gate; research data to the separate fleet's target, client-side encrypted. | `gerchowl/g-fleet#1438` |
| O-11 | Build the warm tier (ZFS raidz2, versitygw, sanoid) and the checksum-verified migration. | `gerchowl/g-fleet#1363` |
| O-12 | Provide the observability seam the hub exports to (freshness, spend, queue, quota alerts). | `gerchowl/g-fleet#1474` (the `s3` seam of `modules/observability/interface.nix`) |

## 8. Open points and decisions taken here

| # | Point | Decision taken here | Settled by |
|---|---|---|---|
| G-1 | Simple quotas on a pool that already holds large images | Enabled once, limits per subvolume; checked on a scratch image first (SYS-011) | O-2 |
| G-2 | Random-read latency through virtiofs | Share the subvolume; fall back to a block-device image if p95 exceeds 1 ms *(estimate)* (section 3) | the measurement of SYS-012 |
| G-3 | Gateway root, bucket-as-subvolume, `current` pointer rule | Proposed in sections 2 and 4 | `gerchowl/g-fleet#1449` (O-6) |
| G-4 | 1 base versus 2 on the KC3000 | 1 base in stage 0, recorded as policy | O-1 |
| G-5 | Add-only rule versus retention; `research` versus corpus | Corpus generations in `keep`; `out/` is never deleted until settled | `gerchowl/g-fleet#1363` (O-8) |
| G-6 | Guest uid mapping for the virtiofs shares | A module detail, not a layout fact | `nerdmachines/scitadel-hub-deploy#2` |

## 9. Stage 1: Hetzner, first hosted users

Tied to XADR-SCITADEL-008 §8, "Stage 1 — Hetzner".

- **Serving.** A Hetzner AX dedicated server runs the hub binary on CPU. The same directory names (`products`, `index`, `staging`, `state`) sit on its local NVMe with the same rules: indexes uncompressed and copy-on-write, `state` the only in-place volume. The AX file system is a choice of that host's module (not specified here); the contract is the rules, not btrfs.
- **Warm.** Hetzner Object Storage replaces the fleet's versitygw as the distribution point for `.tsra` products. The bucket names and tiers are unchanged (SYS-039), only the endpoint is.
- **Cold.** The Storage Box of stage 0 stays the cold tier; the restic layer of section 6 is unchanged.
- **GPU.** anvil remains the steady-state ingest GPU under the same `gpu_submit` policy; hourly-rented Hetzner GPU covers backfills, re-embedding after a model upgrade and spikes (SYS-051).
- **Data flow.** Ingest on anvil seals products and writes them to the distribution bucket; the AX pulls them to its NVMe working copy, as `vm-hub` pulls from `keep` today. Index builds run next to the data they cover.
- **Trigger.** `scitadel-cloud` is extracted at the first external tenant, the first billing code or when serving moves to Hetzner, whichever comes first (XADR-SCITADEL-008 §1).
- **Tests.** The conformance kit, the licence-gating suite, the load test and a restore drill run against it as against stage 0 (SYS-039, SYS-022, SYS-047).

## 10. Stage 2: hosted spaces

Tied to XADR-SCITADEL-008 §8, "Stage 2 — hosted spaces", and §17.

- **Hosting.** NixOS with k3s and microVMs host organisation and personal spaces, one hub instance per tenant on its own microVM with its own state and index volumes (the stage-0 tenant simulation uses this packaging, SYS-035).
- **Shared data.** Sealed products are shared read-only from the distribution bucket; a tenant differs by its annotation layers (SYS-037) and its credentials, not by a different corpus.
- **Metering and billing** sit behind `scitadel-cloud` (SYS-036); this repository holds no commercial figures.
- **GPU.** Backfill and re-embedding continue on hourly-rented Hetzner GPU.
- **Gating.** NC and ND content stays out of every paid tier build (SYS-054), and the commercial route's opt-out handling applies (SYS-055).

## 11. On-prem

Tied to XADR-SCITADEL-008 §8, "On-prem", and §1.

- The NixOS module, OCI image and Helm chart come from the private `nerdmachines/scitadel-hub-deploy` repository, under the commercial grant or a support contract. The AGPL hub source stays public.
- An on-prem hub runs the same binary and the same `.tsra` shards as any stage above and speaks the same protocol (SYS-038).
- Storage contract on the customer's host: the same four hub-local directories, with the indexes on local NVMe, uncompressed and copy-on-write, and `state` on a volume that tolerates in-place writes; the object tiers are any S3-compatible store, or the local file system for a single-host install. Backups and the retention policy are the administrator's, with the same defaults (2 bases and their deltas).
- No hidden outbound dependency: the model weights come through the signed manifest at first run (SYS-056), and fall-through to live sources is configured, not assumed.

## 12. Tier summary

| Tier | Stage 0 (now) | After `gerchowl/g-fleet#1363` | Stage 1 | Stage 2 and on-prem |
|---|---|---|---|---|
| Hot (local NVMe, random access) | KC3000 subvolumes `products`, `index`, `staging`, `state`, `gpu-io` | unchanged | AX local NVMe, same rules | per tenant volume or the customer's NVMe |
| Object tiers | KC3000 buckets via vm-storage (`scratch`, `runs`, `keep`, `research`) | warm ZFS box via versitygw; KC3000 keeps the working set | Hetzner Object Storage | shared read-only distribution bucket, or the customer's S3 |
| Cold | restic to the Storage Box (O-9) | restic from the warm box | unchanged | the administrator's choice on-prem |
