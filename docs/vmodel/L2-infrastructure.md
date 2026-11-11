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

Quotas are hard limits in GiB on the subvolume's qgroup, derived in section 2.4 from a stated size model. They sum to 1,800 GiB, about 1.76 TiB and 65 % of the 2.7 TiB free *(estimate)*. With the 1.0 TiB already used that brings the pool to 74 %, below the 80 % mark of the fill watchdog, and leaves about 995 GiB free, 495 GiB above the 500 GiB guard for the growth of the microVM images. SYS-011 pins the sum (≤ 1,800 GiB) and the alert thresholds.

| Subvolume | Path | Holds | Attributes | Quota (GiB) | Snapshots |
|---|---|---|---|---|---|
| `products` | `$HUB/products` | the hot serving copy of the sealed `.tsra` products: the current base, the compaction candidate, deltas, `current`; embeddings; graph edge tables. A mirror of `keep`, rebuilt by copy | COW, `chattr +m` (no compression) | 335 | none: a mirror of `keep`, and a snapshot would pin retired generations |
| `index` | `$HUB/index` | BM25 (tantivy) and ANN indexes, graph adjacency caches | COW, `chattr +m` | 65 | none (rebuildable) |
| `staging` | `$HUB/staging` | adapter pool and cache, in-flight downloads, internal Parquet staging, and `renders/`, the evictable cache of page renders and region crops (at most 40 GiB, least recently used first) | COW, pool default zstd level 1 | 150 | none |
| `state` | `$HUB/state` | SQLite databases and ledgers (run ledger, subscriptions, credit ledger, freshness, job and hash ledger, retention audit) | **`chattr +C` (nodatacow)** | 20 | hourly, keep 48 h, 14 d, 8 w |
| `gpu-io` | `$HUB/gpu-io` | `in/<run-id>/`, `out/<run-id>/`, `models/` for GPU jobs | COW, `chattr +m` | 100 | none |
| `scitadel-hub-scratch` | `$GW/scitadel-hub-scratch` | bucket, 48 h | COW, pool default | 50 | none |
| `scitadel-hub-runs` | `$GW/scitadel-hub-runs` | bucket, 28 d | COW, pool default | 150 | none |
| `scitadel-hub-keep` | `$GW/scitadel-hub-keep` | bucket, no expiry: the canonical sealed products and their generations, the **raw inputs and cascade intermediates** (the artefact store, logical budget 380 GiB), service definitions by hash, golden fixtures, `state` dumps | COW, pool default | 910 | daily, keep 14 days and 4 weeks |
| `scitadel-hub-research` | `$GW/scitadel-hub-research` | bucket, versioned, write-once when finished | COW, pool default | 20 | daily, keep 14 days, 8 weeks and 12 months |

Why these attributes:

- **No compression (`+m`) on `products`, `index` and `gpu-io`.** Sealed products already carry zstd inside Vortex, embeddings are floating-point vectors, and index files are read by memory-mapped random access: a compressed btrfs extent is up to 128 KiB, so a 4 KiB random read would decompress up to 32 times what it needs. SYS-012 measures the result.
- **Copy-on-write stays on for the indexes.** Tantivy segments and the ANN and adjacency caches are written once and never modified in place (XADR-SCITADEL-008 §4: unsealed, rebuildable, stamped with a seal). `nodatacow` would buy nothing for them and would cost checksums, so silent bit rot would go unseen, and cheap snapshots. The rule used here: **`nodatacow` only where a file is rewritten in place.**
- **`nodatacow` on `state` only.** SQLite with a write-ahead log rewrites pages in place; on copy-on-write that fragments. Hourly snapshots make the first write after each snapshot copy-on-write anyway, so fragmentation is reduced, not removed; that is acceptable for a volume that is small (20 GiB), loses checksums, and is protected by a nightly `PRAGMA integrity_check`, a `.backup` dump into `scitadel-hub-keep`, and the hourly snapshots. The attribute must be set while the subvolume is empty; it applies only to files created afterwards.
- **Any later file that is rewritten in place** (an ANN cache that the L3 design updates in place, for example) goes to a dedicated small `+C` subvolume, never to `index`.
- **Quota mode.** Simple quotas (`btrfs quota enable --simple`): low overhead on a pool that holds 800 GiB-class images and will hold many snapshots. In this mode an extent is charged to the subvolume that created it, so data pinned by a snapshot still counts against its owner until the snapshot expires. Retention deletes therefore free space only after the snapshots covering them age out; the size model of section 2.4 puts that pinned retired generation inside the quota of `keep`.
- **Pool-wide guard.** Alerts at 80 % and 90 % of any quota and below 500 GiB of pool free space (SYS-044). Above 90 % of the pool, and at 90 % of the raw budget of `keep` (section 2.4), the ingest scheduler stops starting work and reports: a pause, never a deletion (SYS-014).

### 2.2 Applying it

Owner action O-2, run as root on anvil. It is **idempotent**: every step reads the current state first, changes only what differs and prints a `changed:` line for each change, so a second run exits 0 and prints none. Existing subvolumes get their limits, attributes and ownership re-applied only where they differ, and `+C` affects only files created afterwards. A path that exists but is not a subvolume aborts the run.

**Run order.** Run it before the hub microVM first boots, because microvm.nix's tmpfiles rules create a missing share source as a plain directory, which would defeat the subvolume, and before O-5. If it is run again after O-5, the project path is a mount point: step 6 detects that with `mountpoint -q` and changes nothing through it. That matters because the bind mount makes the path the root of `gpu-io`, and the `chattr +i` that protects the *unmounted* mount point would otherwise land on the `gpu-io` root and stop every job. The `gpu-io` skeleton is always made through the subvolume path. The environment variables at the top are for the scratch-image drill only. The script is run twice on a scratch image inside a microVM, **never on anvil**, before it is applied (TEST-031).

```bash
#!/usr/bin/env bash
# scitadel-hub stage-0 data layout on the KC3000 pool (anvil-vm). Run as root on anvil.
# Idempotent: every step reads the current state first and changes only what differs.
# A second run exits 0 and prints no "changed:" line.
set -euo pipefail

POOL="${POOL:-/var/lib/microvms}"
POOL_SOURCE="${POOL_SOURCE:-/dev/mapper/anvil-vm}"   # overridden only for the scratch-image drill (TEST-031)
HUB="${POOL}/data/scitadel-hub"
GW="${GW:-${POOL}/data/s3}"                # g-fleet#1449 fixes this path (O-6)
GW_OWNER="${GW_OWNER:-microvm:kvm}"        # the gateway's identity is g-fleet#1449's call
HUB_OWNER="${HUB_OWNER:-microvm:kvm}"
JOB_OWNER="${JOB_OWNER:-larsgerchow:users}"
PROJECT_DIR="${PROJECT_DIR:-/srv/anvil/projects/scitadel-hub}"   # the O-5 mount point, on the 990 PRO
FREE_CHECK="${FREE_CHECK:-1}"              # 0 only on the scratch image
GIB=$((1024 * 1024 * 1024))
BUDGET_GIB=1800
GUARD_GIB=500

note() { echo "changed: $*"; }
die()  { echo "refusing: $*" >&2; exit 1; }

# attr_has PATH LETTER: true when lsattr shows LETTER on the directory itself
attr_has() { [[ "$(lsattr -d "${1}" | cut -d' ' -f1)" == *"${2}"* ]]; }
set_attr() { attr_has "${1}" "${2}" || { chattr "+${2}" "${1}"; note "chattr +${2} ${1}"; }; }

# owner_mode_ok PATH OWNER:GROUP MODE
owner_mode_ok() {
  [[ "$(stat -c '%U:%G' "${1}")" == "${2}" ]] && (( 8#$(stat -c '%a' "${1}") == 8#${3} ))
}
ensure_owner_mode() {
  owner_mode_ok "${1}" "${2}" "${3}" && return 0
  [[ "$(stat -c '%U:%G' "${1}")" == "${2}" ]] || { chown "${2}" "${1}"; note "chown ${2} ${1}"; }
  (( 8#$(stat -c '%a' "${1}") == 8#${3} )) || { chmod "${3}" "${1}"; note "chmod ${3} ${1}"; }
}
ensure_dir() {   # path owner:group mode
  if [[ ! -d "${1}" ]]; then
    install -d -o "${2%%:*}" -g "${2##*:}" -m "${3}" "${1}"; note "created ${1}"
  fi
  ensure_owner_mode "${1}" "${2}" "${3}"
}

# qgroup_limited_to PATH BYTES: true when the subvolume's qgroup already carries that limit.
# Columns of `-re --raw`: qgroupid rfer excl max_rfer max_excl. Simple quotas may report the limit in either column.
qgroup_limited_to() {
  btrfs qgroup show -reF --raw "${1}" | awk -v want="${2}" 'NR > 2 && ($4 == want || $5 == want) { f = 1 } END { exit !f }'
}

# 1. right pool, enough room
[[ "$(findmnt -n -o SOURCE,FSTYPE "${POOL}")" == "${POOL_SOURCE} btrfs" ]] \
  || die "${POOL} is not the ${POOL_SOURCE} btrfs pool"
if [[ "${FREE_CHECK}" == 1 && ! -d "${HUB}" ]]; then   # first run only: later runs hold hub data already
  free_bytes="$(df -B1 --output=avail "${POOL}" | tail -n 1 | tr -d ' ')"
  (( free_bytes > (BUDGET_GIB + GUARD_GIB) * GIB )) || die "pool free space is below budget plus guard"
fi

# 2. simple quotas, once
if ! btrfs qgroup show "${POOL}" >/dev/null 2>&1; then
  btrfs quota enable --simple "${POOL}"; note "simple quotas enabled on ${POOL}"
fi

# 3. directories (plain)
ensure_dir "${POOL}/data" root:root 0755
ensure_dir "${HUB}" root:root 0755
ensure_dir "${GW}" root:root 0755

# 4. subvolume helper: path, limit in GiB, attribute (m, C or -), owner, mode
mk() {
  local path="${1}" limit="${2}" attr="${3}" owner="${4}" mode="${5}"
  if [[ -e "${path}" ]]; then
    btrfs subvolume show "${path}" >/dev/null 2>&1 || die "${path} exists but is not a subvolume"
  else
    btrfs subvolume create "${path}" >/dev/null; note "created subvolume ${path}"
  fi
  if [[ "${attr}" != - ]]; then set_attr "${path}" "${attr}"; fi   # +C affects only files created afterwards
  ensure_owner_mode "${path}" "${owner}" "${mode}"
  if ! qgroup_limited_to "${path}" $(( limit * GIB )); then
    btrfs qgroup limit "${limit}G" "${path}"; note "qgroup limit ${limit}G ${path}"
  fi
}

mk "${HUB}/products"  335 m "${HUB_OWNER}" 0750
mk "${HUB}/index"      65 m "${HUB_OWNER}" 0750
mk "${HUB}/staging"   150 - "${HUB_OWNER}" 0750
mk "${HUB}/state"      20 C "${HUB_OWNER}" 0750
mk "${HUB}/gpu-io"    100 m "${JOB_OWNER}" 2775   # owned by the job user, group users, setgid
mk "${GW}/scitadel-hub-scratch"   50 - "${GW_OWNER}" 0750
mk "${GW}/scitadel-hub-runs"     150 - "${GW_OWNER}" 0750
mk "${GW}/scitadel-hub-keep"     910 - "${GW_OWNER}" 0750
mk "${GW}/scitadel-hub-research"  20 - "${GW_OWNER}" 0750

# 5. gpu-io skeleton, always through the subvolume path, never through PROJECT_DIR
for d in in out models; do ensure_dir "${HUB}/gpu-io/${d}" "${JOB_OWNER}" 2775; done

# 6. the mount point of the O-5 bind mount. Once the bind mount is in place, PROJECT_DIR *is* the gpu-io
#    root, and nothing may be changed through it (an immutable gpu-io root would stop every job).
if mountpoint -q "${PROJECT_DIR}"; then
  echo "skipped: ${PROJECT_DIR} is already the bind mount of gpu-io (O-5 applied)" >&2
else
  # a NEW project directory on the 990 PRO; immutable so an unmounted mount point accepts no job writes (the bind mount is nofail)
  [[ -d "${PROJECT_DIR}" ]] || { install -d -o "${JOB_OWNER%%:*}" -g "${JOB_OWNER##*:}" -m 2775 "${PROJECT_DIR}"; note "created ${PROJECT_DIR}"; }
  if ! owner_mode_ok "${PROJECT_DIR}" "${JOB_OWNER}" 2775; then
    if attr_has "${PROJECT_DIR}" i; then chattr -i "${PROJECT_DIR}"; fi   # an immutable directory cannot be chown'ed
    ensure_owner_mode "${PROJECT_DIR}" "${JOB_OWNER}" 2775
  fi
  set_attr "${PROJECT_DIR}" i
fi

# 7. report
btrfs subvolume list -t "${POOL}"
btrfs qgroup show -re "${POOL}"
lsattr -d "${HUB}"/* "${GW}"/scitadel-hub-*
```

After the script, these checks must hold (they are the manual drill of SYS-011): a second run of the script prints no `changed:` line; `btrfs qgroup show` lists nine limits that sum to 1,800 GiB; `lsattr` shows `m` on `products`, `index` and `gpu-io` and `C` on `state`; `df` on the pool still shows at least 500 GiB free; writing past a limit on a scratch file returns `EDQUOT`.

Ownership of the four hub-side subvolumes `products`, `index`, `staging` and `state` is `microvm:kvm`, like the share sources of vm-dev. How the guest's service user maps onto that is a detail of the NixOS module (`nerdmachines/scitadel-hub-deploy#2`), not of this layout.

### 2.3 Snapshots

btrbk (the pool is "btrbk / snapper compatible" in the host's own notes) takes read-only snapshots into `${POOL}/data/.snapshots/<subvolume>.<UTC stamp>`, a plain directory beside the hub root. Retention is as in the table above. `${POOL}/data/.snapshots` is created by the same owner action (O-3). The policy is exercised by SYS-045.

### 2.4 Size model *(estimate)*

Units: the hot tier in GiB (btrfs), the warm and cold tiers in TB (1 TB = 931 GiB). Every figure is an estimate that the first measurement replaces (SYS-044 records the actuals). The shape is that of XADR-SCITADEL-008 §15: 5 to 10 million licence-clean papers; sealed size 1 to 2.5 TB, whose per-paper formula already contains about 30 KB of text vectors, which is the ~250 million chunks at 512 dimensions in fp16 (256 GB), so the vectors are **not added again** (the first draft of this document added them on top); patent drawings 0.5 to 1.5 TB; about 100 million figures and drawings embedded. §8's "about 1 TB including working copies" is the initial demo, not the phase-1 shape.

**B** is one generation of sealed products with its embeddings (a base with its deltas folded in): low 1.6 TB, central 2.85 TB, high 4.2 TB (papers 1.0, 1.75, 2.5; drawings 0.5, 1.0, 1.5; figure embeddings 100 million × 512 dimensions × 2 bytes = 0.1 TB, 0.2 TB at 1,024 dimensions in the high case).

**R** is everything kept under the raw-retention rule of XADR-SCITADEL-008 §12 (owner decision 2026-11-11): every raw input and every cascade tier's intermediate output. Nothing in it is deleted automatically.

| Kept class | Low (TB) | Central (TB) | High (TB) | Basis |
|---|---|---|---|---|
| Open-access PDFs of PDF-only works | 1.0 | 2.5 | 7.5 | 5, 7, 10 million papers × 20, 30, 50 % PDF-only × 1.0, 1.2, 1.5 MB |
| JATS, TEI and USPTO XML (zstd) | 0.3 | 0.4 | 0.6 | TEI about 8 to 10 GB per 2 million papers, plus JATS and patent XML |
| Bulk snapshots, four quarterly generations | 1.6 | 2.0 | 3.2 | 0.4, 0.5, 0.8 TB per generation (OpenAlex subsets, Crossref, DataCite, PatentsView, retraction list); no deduplication between generations |
| Raw patent drawings | 0.5 | 1.0 | 2.0 | the drawing volume of §15 |
| Cascade T1 to T4 outputs | 0.3 | 0.8 | 3.0 | 0.18, 0.30, 0.50 MB per processed PDF (OCR text, layout, math, vision-language text, zstd) plus 0.1, 0.2, 0.5 TB for the patent cascade |
| **R** | **3.7** | **6.7** | **16.3** | R / B = 2.3, 2.35, 3.9 |

**Warm tier (g-fleet#1363, 20+ TB).** Holds R and the product history: the current and the previous base with their deltas, 2.1 B at steady state (the default retention of SYS-017). At the quarterly compaction the candidate base is added and the retired one stays pinned by snapshots for up to 3 days: 4.1 B at the peak. R is append-only, so snapshots pin nothing in it.

| Warm tier | Low | Central | High |
|---|---|---|---|
| R | 3.7 TB | 6.7 TB | 16.3 TB |
| Products, steady state (2.1 B) | 3.4 TB | 6.0 TB | 8.8 TB |
| **Steady total** | **7.1 TB (35 % of 20 TB)** | **12.7 TB (64 %)** | **25.1 TB (126 %)** |
| Products, compaction peak (4.1 B) | 6.6 TB | 11.7 TB | 17.2 TB |
| **Peak total** | **10.3 TB (52 %)** | **18.4 TB (92 %)** | **33.5 TB (168 %)** |

20 TB holds the low and the central case at steady state, the central one with 36 % headroom. At the central compaction peak it is 92 % full for up to 3 days, which is inside 20 TB but above the 80 % comfort line of a ZFS pool; the high case does not fit. The capacity to ask for (O-13) is therefore at least 24 TB usable (18.4 / 0.8 = 23 TB) for the central case, and about 42 TB (33.5 / 0.8) if the high case materialises. Renders and crops are derived and are not on the warm tier. **Cold** mirrors warm one to one: 12.7 TB at the central steady state, 18.4 TB at the peak; the Storage Box plan must hold that (O-13).

**Stage 0 on the KC3000, before the warm tier exists.** Everything is on the one pool, so the need is: `products` 2.1 B (current plus compaction candidate, deltas of both), `index` 0.4 B (two index generations during a rebuild, each about 0.2 B), `keep` 3.1 B (the current base, the candidate written there first, SYS-059, and the previous base pinned by the soak and by up to four weeks of daily snapshots, plus deltas) **plus** the raw budget R₀ = 2.4 B **plus** 40 GiB for fixtures, state dumps and the crops of confirmed reports, and the fixed volumes `staging` 150, `state` 20, `gpu-io` 100, `scratch` 50, `runs` 150 and `research` 20 (490 GiB). That is 8.0 B + 530 GiB.

| Case | B (GiB) | Need (GiB) | Fits in 1,800 GiB |
|---|---|---|---|
| **Stage-0 slice** | 158 | 1,794 | **yes** |
| §8 initial demo (about 1 TB in total, working copies included) | about 50 | about 930 | yes |
| Phase 1, low / central / high | 1,490 / 2,654 / 3,910 | 12,450 / 21,762 / 31,810 | no: more than the 3,819 GiB disk |
| After the warm tier exists (needs 2.5 B + 510 GiB) | at most 516 | 1,800 | the serving copy of phase 1 central (2.5 B = 6.5 TiB) still does not fit |

**Consequence, stated plainly: phase 1 does not fit on the KC3000 pool.** Stage 0 therefore runs a **slice** of B ≤ 158 GiB, about 6 % of the central case (4 to 11 % across the range; roughly 15 to 35 million of the 250 million chunks). The slice is a manifest pinned in the run record (SYS-057): the same share of every source, chosen with a fixed seed, so that it is representative and reproducible. The quotas of section 2.1 follow: `products` 2.1 × 158 = 332 → 335; `index` 0.4 × 158 = 63 → 65; `keep` 3.1 × 158 + 2.4 × 158 + 40 = 909 → 910 (raw budget R₀ = 380 GiB inside it); the fixed volumes as listed. When the warm tier exists, the canonical copy, R and the history move to it by the checksum-verified copy of SYS-015 and the KC3000 holds the serving copy, so B can grow to about 516 GiB; the full phase-1 serving copy needs stage-1 NVMe or another disk (O-14).

**At the raw budget, ingest pauses; nothing is deleted.** The run ledger sums the bytes of R in `keep`. At 80 % of R₀ an alert fires; at 90 % the scheduler starts no new run and lets running ones finish; at 100 %, or on `EDQUOT`, a run stops at its next write with its state intact and resumes once space exists (SYS-061). The operator then frees space, raises the quota (re-applying O-2 with a new number) or waits for the warm tier. The only class that may be dropped by hand is a re-fetchable open-access PDF whose hash and URL are recorded: `hub raw drop` refuses any other object and audits every use. The staging copy of a file is removed only after its verified copy exists in `keep`; that removes a duplicate, not data. The render cache is the one class the hub evicts by itself, because it is derived and rebuildable from R (SYS-064).

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
| GPU jobs (`gpu_submit`) | `/srv/anvil/projects/scitadel-hub/{in/<run-id>,models,out/<run-id>}` | bind mount of `gpu-io` onto the project path; jobs run as `bash -lc` with cwd `/` and `cd` there themselves (`docs/gpu-jobs.md`) | read `in/<run-id>/` and `models/`; write only a **new** `out/<run-id>/` and `$GPU_JOB_OUT` |
| `vm-dev` | `/srv/anvil/projects/scitadel-hub` through the existing `anvil-projects` virtiofs share, if the bind mount propagates (to verify) | existing share | not a consumer; light inspection only. Note `gerchowl/g-fleet#1402`: `/srv/anvil` is exported read-write into vm-dev, so `gpu-io` is modifiable by any agent there. The hub therefore does not rely on file permissions. It accepts an output only after the checks of SYS-062: the job id and run id are in the ledger, the job's manifest matches the files, the hub itself recorded the hashes at the job's end, and the hub verified a private copy of the files against both. That detects accidents, mix-ups between runs and modification after the job ended; it does not make a compromised job trustworthy, whose content is judged by QC (SYS-007). A read-only export of `/srv/anvil` to vm-dev is the real fix (O-17) |
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
- A job writes **only new files** under `out/<run-id>/`. The fleet's add-only rule for `/srv/anvil` (existing data is never moved, rewritten or deleted, the project's own included) is respected by construction.
- **Both directions of `gpu-io` need an exception to that rule** (owner action O-8, settled in `gerchowl/g-fleet#1363` (H6) as XADR-SCITADEL-008 §2 says): the hub removes old `out/<run-id>/` directories once their output is accepted and promoted, **and its own `in/<run-id>/` copies** within 24 h after the run is accepted. Both are duplicates of data that is kept (raw inputs and intermediates are never deleted, SYS-014, so the copy in `gpu-io` is never the only one). The hub does this through its own virtiofs share of the subvolume, in the ledger, as an audited action of its retention role, and the in-copies are what TEST-034 checks. Until O-8 is settled nothing is deleted, the 100 GiB quota alerts at 80 % and the ingest scheduler stops submitting at 90 %, which pauses GPU work and loses no data.
- **T3 runs on the 5090 by default.** Its stage-0 service definition (SYS-067) targets `gpu_submit` on anvil: the page images are rendered from the kept originals into `in/<run-id>/pages/`, so no data leaves anvil. Sage is only an optional overflow executor (section 3.1).
- Every submission declares VRAM, runs at low priority, is chunked to the default 30-minute runtime with checkpoints under `out/<run-id>/` (SYS-048), and backfills or re-embedding sweeps never run here (SYS-051).
- Serving holds no GPU device (SYS-024).

### 3.1 Other compute hosts

- **ksb (SYS-063).** Nothing reaches ksb implicitly. The hub builds a named slice `ksb-slice-<id>` from the stage-0 slice (a manifest of paths, sizes and blake3 hashes plus the files; CC0, CC-BY and public-domain content only), transfers it by the mechanism of g-fleet docs/ksb-compute.md, the task verifies it against the manifest on arrival, reads it read-only and deletes it at the end. The tests that need the stage-0 corpus on ksb (TEST-021, TEST-029, TEST-030, TEST-038, TEST-041, TEST-042) use this slice. Ksb's capacity for a slice of up to 250 GiB is owner action O-15 (`gerchowl/g-fleet#654` requires an explicit transfer).
- **sage (SYS-070), only if an overflow definition targets sage.** With no enabled service definition naming sage there is no data path and no credential. If one is enabled, the hand-off payload sits under its own prefix of `scitadel-hub-runs`, the T3-worker role (section 4) fetches it with short-lived credentials, the result comes back under the same prefix with a manifest and is accepted under SYS-062, and nothing stays on sage afterwards. The network path from sage to vm-storage is owner action O-16.
- **Service definitions are configuration.** Moving a tier from one executor to another is a new version of its definition in the service registry (SYS-067, SYS-069), with no code change; every run and every row records the definition hash (SYS-068).

**Decision gate G-2 (random-read latency through virtiofs).** The indexes are read by memory-mapped random access, and a guest reads them through virtiofs. SYS-012 measures p95 4 KiB random read through that path. If it exceeds 1 ms *(estimate)*, the `index` subvolume is not shared but holds a sparse raw ext4 image attached to `vm-hub` as a virtio block device, the way vm-dev's images are attached; the quota then caps the image file. The gate is decided by the measurement, not by preference, and the rest of the layout is unaffected.

## 4. Buckets (g-fleet#1449 tiers)

`gerchowl/g-fleet#1449` (owner go 2026-11-09) provides, per project, `<project>-scratch` (48 h), `<project>-runs` (28 d, a warning at 72 h or less remaining), `<project>-keep` (no expiry) and `<project>-research` (indefinite, versioned, write-once when finished). For the project `scitadel-hub`:

| Bucket | Tier meaning | What the hub puts there |
|---|---|---|
| `scitadel-hub-scratch` | 48 h | tenant-simulation staging and temporary copies that can be rebuilt within 48 h. **No queued work and no quarantine**: a weekend must not expire either |
| `scitadel-hub-runs` | 28 d | run manifests, QC and golden-set diff reports, embedding-drift reports, candidate delta products before promotion, copies of job logs, **quarantined inputs awaiting triage** and **cascade hand-off payloads** (T3 and T4 work waiting for budget), whose lifetime of weeks matches this tier |
| `scitadel-hub-keep` | no expiry; products are deleted only by the retention role | the **canonical sealed products** and their generations (`base/<release>/`, `delta/<date>.tsra`, `current`); the **content-addressed raw and intermediate store** (blake3 keys): open-access PDFs, JATS, TEI and USPTO XML, bulk snapshots, T1 to T4 outputs keyed by input hash, tool, model, version and definition hash; the **service definitions** by hash (SYS-067); the private golden fixtures (the non-CC fixture bucket of XADR-SCITADEL-008 §13) with the crops of confirmed reports; unresolved quarantine items (`quarantine/`); nightly `state` dumps |
| `scitadel-hub-research` | versioned, write-once when finished | finished evaluation results only: grounding-benchmark runs on a pinned release, golden-set baselines |

**Expiry behaviour and alerts.** `scratch` and `runs` objects are copies, never the only record: the queue position, the quarantine decision and the budget spend live in the run ledger in `state` (SYS-057), and the payload copies data whose original is kept (SYS-014). The `runs` tier warns at 72 h or less before expiry (SYS-013); the warning raises an alert naming the run and the items. A **queued item whose payload expired is not skipped**: the orchestrator rebuilds the payload from the kept original and puts it again, which starts a new 28-day clock (SYS-006). A **quarantined item still untriaged at the warning** is copied by the hub into `keep/quarantine/`, so the decision outlives the bucket, and the alert says so; a confirmed error becomes a red fixture in `keep`. Hand-off payloads that carry PDF pages are removed by the hub when the run is accepted; expiry is only the backstop.

**Why the corpus is in `keep`, not `research`.** XADR-SCITADEL-008 §2 retires generations by an explicit retention policy (the last two bases and their deltas), while `research` is write-once and indefinite. The two rules meet in `gerchowl/g-fleet#1363` (H6), per the same section. Until that is settled the corpus generations live in `keep`, where one dedicated role may delete a retired generation by policy and nothing else may delete at all (SYS-017). `research` holds only data that is meant to be immutable.

**Roles (gateway accounts and permissions).** Each cell is what the role may do; "create" means a new key and never an overwrite.

| Role | scratch | runs | keep | research |
|---|---|---|---|---|
| hub serving | none | read | read | read |
| hub ingest and promotion | read, write | read, write | create; overwrite **only** the `current` pointer key | create once |
| hub retention (the only deleter) | none | none | delete keys of a retired product generation, after the soak of SYS-060; **never** raw inputs or intermediates | none |
| GPU job (later, short-lived credentials) | read, write | create | none | none (narrower than the #1449 example, see below) |
| T3 overflow worker on sage (only if an overflow definition targets sage, SYS-070) | none | read and create under its own prefix `t3/` | none | none |
| backup agent (restic) | none | none | read, **from the newest read-only btrbk snapshot of the bucket subvolume on the host**, never from the live directory the gateway writes into | the same |
| tenant-simulation account | own buckets only | own buckets only | own buckets only | own buckets only |

The `#1449` example gives GPU jobs read access to `research`. This table deliberately grants none: the hub's GPU jobs read only `in/<run-id>/` and `models/`, and in stage 0 they have no S3 credentials at all. O-6 provisions the narrower role; if a job ever needs a golden baseline, the hub stages it into `in/`.

No role, and no project, can overwrite a finished `research` object or read another project's bucket (SYS-013). Two points are for `#1449` to verify at the pinned versitygw source, as that issue already asks: that a pre-created subvolume directory is adopted as a bucket (otherwise the provisioner creates buckets as subvolumes instead of `mkdir`), that a per-key rule or versioning lets the ingest role move only `current`, and where the gateway keeps object versions (a separate versioning directory would escape the `research` quota, its snapshots and the backup set). If a per-key rule is missing, `current` becomes a sequence of pointer objects with the newest winning, which needs no overwrite.

## 5. Where each kind of data goes

| Data | Location (stage 0) | Why there | Rebuildable | Backed up |
|---|---|---|---|---|
| Adapter pool (bulk files per source: PatentsView tables, weekly grant XML, OpenAlex snapshot parts), the working copy | `staging/adapters/<source>/pool/` | compressible text; the kept, verified copy is the one in `keep`; the staging copy is removed once that copy is verified (a duplicate, not data) | yes, from `keep` | via `keep` |
| Adapter cache (conditional-request responses, pacing state) | `staging/adapters/<source>/cache/` | small, many files; pacing and credit ledgers themselves live in `state` | yes | no |
| In-flight downloads (open-access PDFs, XML) | `staging/downloads/` | `.part` file plus sidecar, resumable by range (SYS-058); on completion verified and written to the artefact store | yes | no |
| Internal Parquet staging, until tessera#778 lands | `staging/parquet/` | never published (XADR-SCITADEL-008 §2) | yes | no |
| Raw inputs, **all** of them: open-access PDFs, JATS, TEI, USPTO XML, bulk snapshots | `scitadel-hub-keep`, artefact store (stage 0, budget 380 GiB); the warm tier later | content-addressed (blake3), never in a product, never deleted automatically (SYS-014); the hub never serves PDF bytes (D-007) | upstream may withdraw them | yes, mirrored cold |
| Cascade intermediates, T1 to T4 (OCR text, layout, math, vision-language and verdict output) | artefact store, keyed by input hash, tool, model, version and definition hash | kept so that a re-derive starts from the stored OCR and not from the GPU (SYS-066) | at GPU cost | yes, mirrored cold |
| Page renders and region crops | `staging/renders/` (hot), derived | rebuildable from the kept originals on demand (SYS-064); evicted least recently used first; only the crop of a confirmed report is kept, as a red fixture in `keep` | yes | no |
| Service definitions | the hub's configuration, each version also by hash in `keep` | versioned, immutable, resolvable from any ledger or provenance hash (SYS-067) | yes | via `keep` |
| `.tsra` products, hot serving copy | `products/<collection>/base|delta/…`, `current` | read locally by the query engine; written to `keep` first, then here (SYS-059) | yes, from `keep` | via `keep` |
| `.tsra` products, canonical copy | `scitadel-hub-keep` (stage 0), then the warm tier | the S3 store of record; the hot copy is a mirror of it | yes | yes |
| Embeddings (one product per model, beside each shard); image embeddings of figures and page regions form a product of their own (SYS-065) | `products/…/embeddings/<model>/` | native Vortex fixed-size lists; about 12 GB for patents and about 51 GB for 50,000,000 chunks at 512 dimensions in fp16; at full phase 1 about 256 GB for 250 million text chunks and about 100 GB for 100 million figures *(estimates)* | yes (GPU cost) | via `keep` |
| BM25 and ANN indexes | `index/bm25/…`, `index/ann/…` | **local NVMe random access**, uncompressed, copy-on-write (SYS-012) | yes, ≤ 24 h *(estimate)* (SYS-021) | no |
| Graph: typed edge tables | `products/…/graph/` | tables are products | yes | via `keep` |
| Graph: adjacency (CSR) cache | `index/graph/` | derived cache | yes | no |
| Hub state: run ledger (SYS-057), subscriptions, credit and freshness ledgers, job and hash ledger, retention audit, metering counters | `state/` (SQLite, `+C`) | small, rewritten in place | partly (ledgers are not) | yes: hourly snapshots, nightly dump to `keep` |
| GPU inputs, outputs, model weights | `gpu-io/{in/<run-id>,out/<run-id>,models}` | visible to `gpu_submit` at the project path; `in/` holds copies of kept data, removed within 24 h of acceptance (O-8); weights fetched at first run through a signed manifest, never baked into an image (SYS-056), and checked against the definition's weights hash (SYS-067) | yes | no |
| QC and diff reports, candidate deltas, quarantined inputs, hand-off payloads | `scitadel-hub-runs` | 28-day working record; the run record itself is in the ledger (`state`) | yes | no |
| Finished benchmark results | `scitadel-hub-research` | immutable by tier | no | yes |
| Secrets | the hub's own `sops` file, `/run/secrets` in the guest | never on any volume above (SYS-040) | n/a | in the fleet's secrets backup |

The hot copy and the canonical copy of a sealed product are two separate byte copies on the same disk until the warm tier exists. The quotas account for both: `products` holds 2.1 B and `keep` holds 3.1 B plus R, as derived in section 2.4 (the first draft set `keep` below `products` and overlooked that).

### 5.1 One ingest run, hop by hop

1. **Open the run (SYS-057).** The orchestrator writes the run record to the ledger in `state`: every input pinned by version or snapshot date and hash, the slice manifest, the code and configuration versions and the hash of each service definition (SYS-067, SYS-068). An unpinned input stops the start.
2. **Download (SYS-058).** Into `staging/downloads/` as a `.part` file with a sidecar; range resume after any interruption; accepted only when size and hash match the source, or recorded with its own hash. Pacing and opt-out checks (SYS-055) apply to every request.
3. **Keep the raw (SYS-014).** The verified file is written to the artefact store in `keep` by blake3 key and read back; then the staging copy goes. In stage 0 this is bounded by the raw budget; at 90 % ingest pauses with an alert (section 2.4).
4. **Cascade.** T0 on CPU in `vm-hub`. T1 and T3 as GPU jobs: the hub stages `in/<run-id>/`, submits through `gpu_submit` under the executor and limits of the tier's service definition, and accepts the output only under SYS-062 (section 3); the accepted output is written to the artefact store as an intermediate. T2 and T4 as the definitions say. Queued T3 and T4 work waits in the ledger, its payloads in `runs` (section 4).
5. **Seal.** Shards are built in `staging` and hashed.
6. **Write order (SYS-059).** Each shard goes to `keep` first, is read back and verified, then copied to `products` and verified. `current` does not move.
7. **QC and promotion (SYS-060).** The candidate passes the QC gate; then `current` is switched in `keep` and, by atomic rename, in `products`. The previous generation stays for at least 7 days; rollback is a re-point.
8. **Clean up.** `in/<run-id>/` copies are removed within 24 h (O-8); hand-off payloads that carry pages are removed; the ledger keeps every hash. Raw inputs and intermediates are not removed.
9. **A crash at any point (SYS-061)** resumes at the first incomplete step; completed steps whose recorded outputs still verify are skipped, partial outputs are discarded.

**Image processing (SYS-064 to SYS-066).** The kept originals feed three things. Page renders and region crops are made on demand into `staging/renders/` and are derived and evictable: a report on a bad table is shown against its source region, the element is re-extracted from it, and only the crop of a confirmed report is kept, as a red fixture in `keep`. Image embeddings of figures and page regions (Qwen3-VL-Embedding) run as GPU jobs under the same acceptance rules. A vision tier can be re-run on demand from the stored inputs, writing new intermediates beside the old. A crop shown to a reporting user is a licence-gated derived image; PDFs are never served.

## 6. Durability

In order of when each layer exists.

1. **Snapshots (btrfs, stage 0 now)**, SYS-045. They protect against accidental deletion and overwrite. They do **not** protect against loss of the KC3000, of anvil or of the LUKS key: a snapshot shares the disk with its source.
2. **Off-box encrypted backup (restic to a Hetzner Storage Box)**, SYS-046, SYS-016. Nightly, client-side encrypted, keys only in the fleet's `sops`. The backup set is exactly the non-rebuildable data: `scitadel-hub-keep` (canonical products, raw inputs and intermediates), `scitadel-hub-research` and the `state` dumps, read from the newest read-only snapshot and not from the live gateway directory. Once the warm tier exists the cold tier is a one-to-one mirror of it (section 2.4). Retention in the repository: 14 daily, 8 weekly, 12 monthly. A monthly `restic check --read-data-subset=5%`. The Storage Box does not accept `zfs receive`, which is why this layer is restic (or borg) and not block replication. It can start **before** the storage host exists, because it needs no ZFS (owner action O-9).
3. **Interim target (`gerchowl/g-fleet#1438`).** The fleet's decided interim backup is the vm-storage S3 on this same KC3000, separate from the 990 PRO. For hub data that already lives on the KC3000 it adds no failure domain, so it is not counted here. Research data follows the owner's refinement of `#1438`: a client-side-encrypted push to the separate fleet's target, with a restore drill and `restic check` before any research cutover.
4. **Replication to the storage host (`gerchowl/g-fleet#1363`), once it exists.** The canonical bucket contents, with the raw inputs, the intermediates and the product history, move to the warm S3 box by a checksum-verified copy (`rclone copy --checksum`, then a listing and hash compare that must show 0 differences, SYS-015), the hub's S3 endpoint is flipped by configuration, and the KC3000 buckets shrink to the hot working set. The box then snapshots with sanoid and ships off-site with restic to the Storage Box (the same layer 2, now sourced from the warm box).
5. **Restore drill, quarterly and before any keep or research cutover**, SYS-047: an empty microVM, the backup set, rebuilt indexes, the smoke suite and the golden queries, within 8 h *(estimate)* (OUT-017).

**What is and is not at risk before layer 2 exists.** Until the first off-box backup runs, hub data has a single failure domain. In phase 1 almost all of it is rebuildable from public upstreams. What is not: the content-API TEI (paid per fetch), the kept raw inputs and intermediates (re-fetchable only while upstream still serves them, and re-derivable only at GPU cost), the private golden fixtures, finished research results and the `state` ledgers. Until layer 2 and its first successful restore drill exist, those are the reason not to cut over `keep` or `research` for real use (the gate of `#1438`).

## 7. Owner actions

Nothing here has been filed or changed. Each item names the g-fleet issue that owns it; "to file" gives a proposed title.

| # | Action | Owner issue |
|---|---|---|
| O-1 | Decide whether stage-0 retention on the KC3000 is 1 base and its deltas plus the previous base for a 7-day soak after each promotion (proposed here, in SYS-017) rather than the default 2, until the warm tier exists. The quotas of section 2.4 hold the current, the candidate and the previous base in `keep`. | `gerchowl/g-fleet#1363` |
| O-2 | Enable simple quotas on the `anvil-vm` pool and apply the layout script of section 2.2 (subvolumes, attributes, limits) before the hub microVM first boots. | to file: "anvil: scitadel-hub stage-0 data subvolumes and quotas on the KC3000 pool" (related `#1474`) |
| O-3 | Install the btrbk policy of section 2.3 for the hub subvolumes. | to file: "anvil: btrbk snapshot schedule for the scitadel-hub subvolumes" (related `#1438`) |
| O-4 | Register the hub budget (1,800 GiB, nine limits) with the pool's fill watchdog and budget check. | to file: "anvil-vm pool: register the scitadel-hub subvolume budget with the fill watchdog" (module `anvil-vm-pool.nix`) |
| O-5 | Add the bind mount of `gpu-io` at `/srv/anvil/projects/scitadel-hub` and check that `vm-dev` sees it through `anvil-projects`. | to file: "anvil: bind the scitadel-hub gpu-io subvolume at /srv/anvil/projects/scitadel-hub" (related `#1402`) |
| O-6 | Provision `scitadel-hub-{scratch,runs,keep,research}` per tier. Fix the gateway root (proposed `/var/lib/microvms/data/s3`), make each hub bucket a btrfs subvolume (or adopt the pre-created ones), and verify per-key rules or versioning for the `current` pointer. | `gerchowl/g-fleet#1449` (depends on `#1377` for vm-storage's RAM slot) |
| O-7 | Define `vm-hub` (the hub as a microVM) with the five virtiofs shares of section 3, importing the private module without patching it; hub secrets in their own `sops` file. | `gerchowl/g-fleet#1474` (blocked on `nerdmachines/scitadel-hub-deploy#2`) |
| O-8 | Settle how the add-only rule for `/srv/anvil` meets the hub's removal of old `out/<run-id>/` directories and of its own `in/<run-id>/` copies, and how `research` meets corpus generations. | `gerchowl/g-fleet#1363` (H6 per XADR-SCITADEL-008 §2) |
| O-9 | Provision the Hetzner Storage Box and the restic repository, keys only in `sops`, nightly job and monthly check, before the storage host exists. | to file: "backup: restic of scitadel-hub keep and research to the Hetzner Storage Box" (related `#1263`, `#1363`) |
| O-10 | Interim backup target and the restore drill gate; research data to the separate fleet's target, client-side encrypted. | `gerchowl/g-fleet#1438` |
| O-11 | Build the warm tier (ZFS raidz2, versitygw, sanoid) and the checksum-verified migration. | `gerchowl/g-fleet#1363` |
| O-12 | Provide the observability seam the hub exports to (freshness, spend, queue, quota alerts). | `gerchowl/g-fleet#1474` (the `s3` seam of `modules/observability/interface.nix`) |
| O-13 | **Warm host capacity and date.** Confirm the usable capacity of the warm host (the owner's figure is 20+ TB) and the date it becomes available. The size model of section 2.4 needs at least 24 TB usable for the central case to stay under 80 % at the compaction peak, and about 42 TB for the high case. The Storage Box plan must hold the warm set one to one (12.7 TB central steady state, 18.4 TB at the peak). | `gerchowl/g-fleet#1363` (cold mirror: `gerchowl/g-fleet#1438`) |
| O-14 | **Hot capacity for full phase 1.** The KC3000 holds at most a base of about 516 GiB even with the warm tier; the central phase-1 serving copy needs 2.5 B, about 6.5 TiB of NVMe. Decide between the stage-1 AX local NVMe (XADR-SCITADEL-008 §8) and an additional disk. | to file: "anvil or AX: hot NVMe capacity for the full phase-1 serving copy" (related `gerchowl/g-fleet#1363`) |
| O-15 | Confirm ksb's capacity for a corpus slice of up to 250 GiB and the transfer mechanism for it (explicit, hash-verified). | `gerchowl/g-fleet#654` (docs/ksb-compute.md) |
| O-16 | Only if an overflow definition targets sage: the network path from sage to vm-storage and the T3-worker credentials. | `gerchowl/g-fleet#1449`, `gerchowl/g-fleet#1474` |
| O-17 | Export `/srv/anvil` read-only to vm-dev, or `gpu-io` at least, so that no agent there can modify GPU inputs and outputs. | `gerchowl/g-fleet#1402` |

## 8. Open points and decisions taken here

| # | Point | Decision taken here | Settled by |
|---|---|---|---|
| G-1 | Simple quotas on a pool that already holds large images | Enabled once, limits per subvolume; checked on a scratch image first (SYS-011) | O-2 |
| G-2 | Random-read latency through virtiofs | Share the subvolume; fall back to a block-device image if p95 exceeds 1 ms *(estimate)* (section 3) | the measurement of SYS-012 |
| G-3 | Gateway root, bucket-as-subvolume, `current` pointer rule | Proposed in sections 2 and 4 | `gerchowl/g-fleet#1449` (O-6) |
| G-4 | 1 base versus 2 on the KC3000 | 1 base plus the previous one for a 7-day soak in stage 0, recorded as policy | O-1 |
| G-7 | Raw retention and capacity | Keep every raw input and intermediate; stage 0 within a budget of 380 GiB, pause at 90 %, never delete; the stage-0 slice is B ≤ 158 GiB (section 2.4) | O-13, O-14 |
| G-8 | Where T3 runs | The 5090 via `gpu_submit` by default; sage only as an optional overflow, by service definition | O-16 |
| G-5 | Add-only rule versus retention; `research` versus corpus | Corpus generations in `keep`; `out/` is never deleted until settled | `gerchowl/g-fleet#1363` (O-8) |
| G-6 | Guest uid mapping for the virtiofs shares | A module detail, not a layout fact | `nerdmachines/scitadel-hub-deploy#2` |

## 9. Stage 1: Hetzner, first hosted users

Tied to XADR-SCITADEL-008 §8, "Stage 1 — Hetzner".

- **Serving.** A Hetzner AX dedicated server runs the hub binary on CPU. The same directory names (`products`, `index`, `staging`, `state`) sit on its local NVMe with the same rules: indexes uncompressed and copy-on-write, `state` the only in-place volume. The AX file system is a choice of that host's module (not specified here); the contract is the rules, not btrfs.
- **Warm.** Hetzner Object Storage replaces the fleet's versitygw as the distribution point for `.tsra` products. The bucket names and tiers are unchanged (SYS-039), only the endpoint is. The raw inputs and intermediates stay on the warm ZFS host.
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
| Object tiers | KC3000 buckets via vm-storage (`scratch`, `runs`, `keep` with raw and intermediates within its budget, `research`) | warm ZFS box via versitygw holds raw, intermediates and product history; KC3000 keeps the serving copy | Hetzner Object Storage | shared read-only distribution bucket, or the customer's S3 |
| Cold | restic to the Storage Box (O-9) | restic from the warm box, a one-to-one mirror | unchanged | the administrator's choice on-prem |
