# L2: infrastructure

How the system requirements of [L2](L2-system-requirements.md) are met on hardware: stage 0 on anvil's KC3000 in enough detail to apply as written, then stages 1 and 2 and on-prem as shorter sketches tied to the staged text of the decision record. Every claim about a system requirement cites its `SYS` node; every test is in the [verification plan](L2-verification-plan.md).

> **Source legend.** `XADR-SCITADEL-008` is the vig-os/scitadel decision record "scitadel-hub: a lab corpus server" (ADR 008, status Proposed, [pull request 317](https://github.com/vig-os/scitadel/pull/317)); `§N` is a section of it. `gerchowl/g-fleet#N` is an issue of the private fleet repository, written in code style because it cannot be linked from this public repository. A figure marked *(estimate)* is a first value to be calibrated by the first measurement. This document specifies no commercial figures.

## 1. Facts the layout rests on

Read-only probes of anvil on 2026-11-09 (`lsblk`, `findmnt`, `df`, `btrfs filesystem usage`, `btrfs subvolume list`, `btrfs qgroup show`), plus the g-fleet module that owns the pool (`modules/anvil-vm-pool.nix`).

| Fact | Value | Consequence |
|---|---|---|
| The KC3000 | 4 TB (3.73 TiB), on the chipset at PCIe Gen4 x4, LUKS2, then btrfs (`-d single -m dup`, label `anvil-vm`), mapped as `/dev/mapper/anvil-vm` | **Not ZFS.** Never design against a ZFS pool on the KC3000. ZFS exists only in the future warm store of `gerchowl/g-fleet#1363`, on separate HDDs (the warm-tier row below). |
| Mount | `/var/lib/microvms`, the pool's top level (`subvolid=5`), options `noatime,compress=zstd:1,ssd,discard=async,space_cache=v2` | Compression is pool-wide (zstd level 1). A subvolume can switch it off but cannot pick another level. |
| Space | about 1.0 TiB used, about 2.7 TiB free (`df` shows 2.8 T; the issue's "about 2.9 TB" in decimal units) | The hub budget below is sized against this. |
| Existing content | `vm-dev` and `vm-runner` directories with raw ext4 images (vm-dev `home.img` 768 GiB, `nix-rw.img` 512 GiB, both sparse), logs. **No subvolumes** below the top level; **quotas not enabled** | Everything below is new. Quotas have to be switched on first. |
| Kernel and tools | Linux 7.2.9, btrfs-progs 7.1 | Simple quotas (squota) are available. |
| Who else uses the pool | The g-fleet pool module watches fill at 80 % and 90 % and checks guest image budgets at boot (`storage-budget-sizematch`); `vm-storage` (versitygw) is to run on it (`gerchowl/g-fleet#1449`) and was **not deployed** on the probe date | The hub budget must be registered with that module (owner action O-4), and the bucket path is `#1449`'s to confirm (O-6). |
| Warm tier (owner statement, 2026-11-18; not probed) | **20+ TB of HDD attached to anvil**, served through the versitygw/ZFS store of `gerchowl/g-fleet#1363` (XADR-SCITADEL-008 §8, stage 0). The ZFS layout (raidz2 or mirror) is the owner's or g-fleet's call | The hot (KC3000 NVMe) and warm (HDD) tiers are different disks in **one host**, so they share one failure domain. The cold mirror on the Storage Box is the only off-anvil copy of the raw data (section 6). Usable capacity after the ZFS layout is O-13 |
| `/srv/anvil` | On the **990 PRO** (`/home`, `/srv`, 76 % used, 458 GB free), **not** on the KC3000 | XADR-SCITADEL-008 §8 says the KC3000 holds the working copy "under `/srv/anvil/projects/<project>/`". That path is only reachable by a bind mount from the KC3000 (section 3). |

## 2. Stage 0: the layout on the KC3000

Two roots, both new, both plain directories created by root:

- `HUB=/var/lib/microvms/data/scitadel-hub` holds the hub's own subvolumes.
- `GW=/var/lib/microvms/data/s3` is the proposed POSIX backend root of the vm-storage gateway; the four hub buckets are subvolumes inside it. **The path is a proposal; `gerchowl/g-fleet#1449` fixes it** (owner action O-6). The apply script takes it as one variable.

The `data/` directory keeps project data apart from the microVM directories that microvm.nix manages directly under `/var/lib/microvms/`.

### 2.1 Subvolumes

Quotas are hard limits in GiB on the subvolume's qgroup, derived in section 2.4 from a stated size model. They sum to 1,840 GiB, about 1.80 TiB and 67 % of the 2.7 TiB free *(estimate)*. With the 1.0 TiB already used that brings the pool to 75 %, below the 80 % mark of the fill watchdog, and leaves about 925 GiB free (2.7 TiB is 2,765 GiB, less the 1,840 GiB of quotas), 425 GiB above the 500 GiB guard for the growth of the microVM images. SYS-011 pins the sum (≤ 1,840 GiB) and the alert thresholds.

| Subvolume | Path | Holds | Attributes | Quota (GiB) | Snapshots |
|---|---|---|---|---|---|
| `products` | `$HUB/products` | the hot serving copy of the sealed `.tsra` products: the current base, the compaction candidate, deltas, `current`; embeddings; graph edge tables. A mirror of `keep`, rebuilt by copy | COW, `chattr +m` (no compression) | 435 | none: a mirror of `keep`, and a snapshot would pin retired generations |
| `index` | `$HUB/index` | BM25 (tantivy) and ANN indexes, graph adjacency caches | COW, `chattr +m` | 10 | none (rebuildable) |
| `staging` | `$HUB/staging` | adapter pool and cache, in-flight downloads, internal Parquet staging, `build/<run-id>/` (shards being sealed), `models/<weights blake3>/` (query-embedder weights), `gpu-accept/<run-id>/` (accepted GPU output before its write), all inside this quota ([DES-021](../architecture/adapters-and-pool.md)), and `renders/`, the evictable cache of page renders and region crops (at most 40 GiB, least recently used first) | COW, pool default zstd level 1 | 150 | none |
| `state` | `$HUB/state` | SQLite databases and ledgers (run ledger, subscriptions, credit ledger, freshness, job and hash ledger, retention audit) | **`chattr +C` (nodatacow)** | 20 | hourly, keep 48 h, 14 d, 8 w |
| `gpu-io` | `$HUB/gpu-io` | `in/<run-id>/`, `out/<run-id>/`, `models/` for GPU jobs | COW, `chattr +m` | 100 | none |
| `scitadel-hub-scratch` | `$GW/scitadel-hub-scratch` | bucket, 48 h | COW, pool default | 50 | none |
| `scitadel-hub-runs` | `$GW/scitadel-hub-runs` | bucket, 28 d | COW, pool default | 150 | none |
| `scitadel-hub-keep` | `$GW/scitadel-hub-keep` | bucket, no expiry: the canonical sealed products and their generations, the **raw inputs and cascade intermediates** (the artefact store, logical budget R₀ = 195 GiB, section 2.4), service definitions by hash, golden fixtures, nightly `state` dumps (the newest 7, section 2.4) | COW, pool default | 905 | daily, keep 14 days and 4 weeks |
| `scitadel-hub-research` | `$GW/scitadel-hub-research` | bucket, versioned, write-once when finished | COW, pool default | 20 | daily, keep 14 days, 8 weeks and 12 months |

Why these attributes:

- **No compression (`+m`) on `products`, `index` and `gpu-io`.** Sealed products already carry zstd inside Vortex, embeddings are floating-point vectors, and index files are read by memory-mapped random access: a compressed btrfs extent is up to 128 KiB, so a 4 KiB random read would decompress up to 32 times what it needs. SYS-012 measures the result.
- **Copy-on-write stays on for the indexes.** Tantivy segments and the ANN and adjacency caches are written once and never modified in place (XADR-SCITADEL-008 §4: unsealed, rebuildable, stamped with a seal). `nodatacow` would buy nothing for them and would cost checksums, so silent bit rot would go unseen, and cheap snapshots. The rule used here: **`nodatacow` only where a file is rewritten in place.**
- **`nodatacow` on `state` only.** SQLite with a write-ahead log rewrites pages in place; on copy-on-write that fragments. Hourly snapshots make the first write after each snapshot copy-on-write anyway, so fragmentation is reduced, not removed; that is acceptable for a volume that is small (20 GiB), loses checksums, and is protected by a nightly `PRAGMA integrity_check`, a zstd-compressed `.backup` dump into `scitadel-hub-keep` (bounded retention, section 2.4), and the hourly snapshots. The attribute must be set while the subvolume is empty; it applies only to files created afterwards.
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
BUDGET_GIB=1840
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

mk "${HUB}/products"  435 m "${HUB_OWNER}" 0750
mk "${HUB}/index"      10 m "${HUB_OWNER}" 0750
mk "${HUB}/staging"   150 - "${HUB_OWNER}" 0750
mk "${HUB}/state"      20 C "${HUB_OWNER}" 0750
mk "${HUB}/gpu-io"    100 m "${JOB_OWNER}" 2775   # owned by the job user, group users, setgid
mk "${GW}/scitadel-hub-scratch"   50 - "${GW_OWNER}" 0750
mk "${GW}/scitadel-hub-runs"     150 - "${GW_OWNER}" 0750
mk "${GW}/scitadel-hub-keep"     905 - "${GW_OWNER}" 0750
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

After the script, these checks must hold (they are the manual drill of SYS-011): a second run of the script prints no `changed:` line; `btrfs qgroup show` lists nine limits that sum to 1,840 GiB; `lsattr` shows `m` on `products`, `index` and `gpu-io` and `C` on `state`; `df` on the pool still shows at least 500 GiB free; writing past a limit on a scratch file returns `EDQUOT`.

Ownership of the four hub-side subvolumes `products`, `index`, `staging` and `state` is `microvm:kvm`, like the share sources of vm-dev. How the guest's service user maps onto that is a detail of the NixOS module (`nerdmachines/scitadel-hub-deploy#2`), not of this layout.

### 2.3 Snapshots

btrbk (the pool is "btrbk / snapper compatible" in the host's own notes) takes read-only snapshots into `${POOL}/data/.snapshots/<subvolume>.<UTC stamp>`, a plain directory beside the hub root. Retention is as in the table above. `${POOL}/data/.snapshots` is created by the same owner action (O-3). The policy is exercised by SYS-045.

### 2.4 Size model (measured on a sample, S-013)

Units: the hot tier in GiB (btrfs), the warm and cold tiers in TB (1 TB = 931 GiB). **This section is the one place where sizes are derived.** Every other node (SYS-015, OUT-004, O-13, O-14, G-7 and the quotas of section 2.1) links here and does not restate a figure. Each number says where it comes from: *measured (n = …)* is a per-paper factor of the S-013 sample or, for the sealed products, the figures and the snapshot generations, of its S-015 re-run on the same works (the source of each is in the tables), and *modelled* is a value of the first size model that no measurement has replaced.

**Planning case.** The owner ruled S-014 (#88, 2026-11-22): phase 1 is the licence-clean **scholarly types**, `type` in article, review, preprint and conference-paper. The **planning case is those 23.2 million works, central case, at the compaction peak**; the articles alone and all types are shown beside it for comparison only (next table). Datasets, paratext, components and the other types are outside phase 1.

**Sample.** `tools/sizing/data/manifest.json`: 10,000 works drawn from OpenAlex with `filter=best_oa_location.license:cc-by|cc0|public-domain&sample=10000&seed=83` on 2026-11-22, paged at 100 (C-003). This is a **uniform sample of the licence-clean set**, not the "same share of every source in the stage-0 source list" that #83 proposed: OpenAlex's licence field is the sample frame, the other stage-0 sources (#82) have no licence-filtered frame here, and a uniform sample weights each source by its share of the licence-clean set. `tools/sizing` ran on ksb with pdftotext (poppler 26.11.0), the Qwen3-Embedding tokenizer (`tokenizers` 0.23.3, hash in `data/measurements.json`; the model is a service-definition choice per SYS-067), tantivy-py (tantivy v0.26.2), pyarrow 24.0.0 and zstd level 3. It fetched the raw bytes, ran the CPU text tier, counted chunks and built a BM25 index; it embedded nothing and kept nothing. A CI is the 95 % percentile bootstrap (1,000 rounds, seed 83) of the mean; **low, central and high** use its lower bound, the mean and its upper bound with the measured population. The CIs are narrow, so the spread between the cases comes mostly from the *modelled* parts (the patent part, T1 to T4, the vector dimensions, the unmeasured snapshot sources). PDFs that could not be fetched are imputed at the mean fetched size, which adds no variance; the lower CI bound of the PDF bytes is therefore the one with failures counted as zero, and the upper bound is narrower than the truth.

**The sealed products (S-015, #89).** The same sample re-run by `tools/sizing tsra` (one ksb batch job, `s015-tsra-3`, 4219 s on 2026-11-22; the data is `tools/sizing/data/tsra.json`) for the scholarly types: n = 6,246 works, with the same fallback from JATS to PDF as S-013. It reached text for **3,189 works** (1,021 JATS, 2,168 PDF) against S-013's 3,378 (JATS 1,455): Europe PMC answered fewer requests, as in the S-013 rerun (the BM25 row of the factor table), so the S-015 factors carry that route mix. The route moves the figure term most: 2,043 KB of lossless figures per JATS work (n = 1,021) against 643 KB per PDF work (n = 2,168), so at S-013's route mix (39.3 % JATS) the planning case's figure blobs would be 20.7 TB, not 18.9 TB. The text of each work is split into the elements of the document model ([document model](../architecture/document-model.md): JATS paragraphs, headings and captions; for a PDF the blocks of `pdftotext -bbox-layout`, so with page and box) and chunked at 350 tokens (37.0 chunks per paper with text against S-013's 35.8: the block split differs from the blank-line split). The tables are written as tessera `.tsra` (0.1.0a1, vig-os/tessera `dev` at `f390528`, built by tessera's own Nix flake on ksb), each as one block for the whole sample, with Parquet zstd level 3 (the reference) and the raw Arrow bytes beside it. **Encoding path.** Tessera writes every document-model table and the metadata: its table columns are fixed-width numbers, booleans and UTF-8 strings. Two shapes fall back to raw Vortex (`vortex-data` 0.93.0, the version tessera links): the vector column, which tessera cannot write as a `fixed_size_list` (vig-os/tessera#768; its array block is measured beside it), and the figure blobs, which need a binary column (vig-os/tessera#779). A tessera product adds 1,932 bytes of manifest and seal to a one-row Vortex file (4,196 against 2,264), paid once per product, so the manifest is below 0.01 % of a shard of 1 GB or more; the Vortex binary column adds 0.012 % to the blob bytes (n = 2,000 figures). A table's size per paper falls slowly with the block size (more rows share dictionaries); the ten random 80 % subsets of the works give the range of the S-015 factors below, which is narrow (the 80 % blocks are within 1.1 % of the whole).

**The population is larger than the first model's scope.** `meta.count` of the licence filter is **36,911,825 works** (measured 2026-11-22, OpenAlex snapshot 2026-10-14). The planning case, `filter=best_oa_location.license:cc-by|cc0|public-domain,type:article|review|preprint|conference-paper`, is **23,239,779 works**: articles 19,935,832, conference papers 1,337,720, preprints 1,196,458 and reviews 769,769 (`group_by=type`). The first model assumed 5 to 10 million. Every per-paper term scales linearly with the scope; the first model's 7 million is shown for comparison.

**The conference-paper type.** OpenAlex's own work type is `conference-paper` (its work-types vocabulary: a complete paper presented at a meeting, usually published in proceedings, which includes Crossref's `proceedings-article`; documented at help.openalex.org/data/work-types, checked 2026-11-22), so the filter is `type:conference-paper`: 1,337,720 works. Two other `meta.count` checks (the manifest records all three): `primary_location.source.type:conference` gives 1,134,755 and the two together 997,812. The source filter is not used: it selects by the type of the venue, not of the work, and 137,000 of its works (12 %) are not typed `conference-paper` by OpenAlex, so the work type, which is the documented field and the one the ruling names, is the definition. The choice moves the count by at most that overlap. `type_crossref` is not a filter of the works endpoint (the API refused it) and was not used. The sample subset of these types has **n = 6,246** of the 10,000 works (62.5 %, against 63.0 % of the population), and every factor below is measured on that subset, the BM25 ratio included (the index is rebuilt over the subset's texts).

**The three scopes side by side** (low / central / high within each; the planning case is the Scholarly types central column; the articles and all types reuse the scholarly types' per-paper tessera and figure factors):

| | Scholarly types low | Scholarly types central | Scholarly types high | Articles (comparison) low | Articles (comparison) central | Articles (comparison) high | All types (comparison) low | All types (comparison) central | All types (comparison) high |
|---|---|---|---|---|---|---|---|---|---|
| Population (million) | 23.2 | 23.2 | 23.2 | 19.9 | 19.9 | 19.9 | 36.9 | 36.9 | 36.9 |
| B (TB) | 16.9 | 21.3 | 26.8 | 14.6 | 18.6 | 23.4 | 18.3 | 23.2 | 29.3 |
| R (TB) | 15.2 | 23.8 | 28.7 | 13.1 | 19.8 | 24.2 | 16.6 | 26.4 | 31.8 |
| Warm steady (TB) | 50.7 | 68.6 | 85.0 | 43.8 | 58.8 | 73.3 | 55.0 | 75.1 | 93.4 |
| Warm peak (TB) | 67.5 | 89.9 | 112 | 58.4 | 77.4 | 96.7 | 73.3 | 98.3 | 123 |
| Usable ask, peak / 0.8 (TB) | 84 | 112 | 140 | 73 | 97 | 121 | 92 | 123 | 153 |
| Hot steady (TB) | 1.5 | 1.7 | 2.7 | 1.3 | 1.5 | 2.3 | 1.7 | 1.9 | 3.0 |
| Hot peak (TB) | 2.9 | 3.3 | 5.2 | 2.6 | 2.9 | 4.5 | 3.2 | 3.7 | 5.8 |
| Hot peak, int8 vectors (TB) | 2.3 | 2.5 | 3.5 | 2.0 | 2.2 | 3.1 | 2.6 | 2.8 | 4.0 |
| Cold (TB) | 116 | 152 | 190 | 101 | 131 | 165 | 126 | 166 | 208 |

| Factor (scholarly types, n = 6,246 works) | Measured (mean, 95 % CI) | First model | Provenance |
|---|---|---|---|
| Papers in the population | 23,239,779 scholarly types (planning case); 19,935,832 articles; 36,911,825 works | 5 / 7 / 10 million *(estimate)* | measured (`meta.count`, `group_by=type`) |
| PDF-only share (no PMC JATS) | 52.1 % (50.9 % to 53.3 %); n = 6,246 | 20 / 30 / 50 % | measured |
| JATS via Europe PMC | 22.5 %; n = 6,246 | not split out | measured |
| Landing page only (no JATS, no PDF location) | 25.4 %; n = 6,246 | not split out | measured; metadata only until #86 |
| PDF bytes per PDF-only work, fetched | 1.21 (1.11 to 1.32) MB; median 0.54; p90 2.6; n = 2,005 | 1.0 / 1.2 / 1.5 MB | measured |
| PDF-route works not fetched (HTTP errors, robots, not a PDF) | 20.1 % of the works | none | measured; imputed at the mean fetched size |
| JATS bytes per paper (zstd) | 5.88 (5.57 to 6.17) KB; n = 6,246 | TEI about 4.5 KB per PDF-only work | measured (JATS); TEI modelled |
| Text bytes per paper with text | 38.1 (37.2 to 39.1) KB; median 33.1; p90 68.2; n = 3,378 | about 20 KB (XADR-SCITADEL-008 §9) | measured |
|   of which JATS route / pdftotext route | 33.3 KB (n = 1,455) / 43.7 KB (n = 2,243) |  | measured; see the bias note below |
| Text bytes per paper (zstd) | 13.4 (13.1 to 13.8) KB; n = 3,378 | 5 to 8 KB (document-model) | measured |
| Chunks per paper at 350 tokens | 35.8 (34.8 to 36.8); median 30; p90 65; n = 3,378 | about 36 (250 million / 7 million) | measured |
|   of which JATS route / pdftotext route | 28.5 / 42.7 |  | measured |
| Chunks per paper at 300 / 400 tokens | 41.5 / 31.5 |  | measured (sensitivity bounds) |
| Text vector bytes per paper (512 dimensions, fp16) | 36.7 KB | about 30 KB | derived: the measured chunk count × the measured bytes per vector (next rows) |
| Bytes per vector, 512 dimensions, fp16 / int8 plus scale (raw 1,024 / 516 B) | Vortex `fixed_size_list` 1,024 / 515 B; tessera array block 885 / 486 B; Parquet zstd 966 / 483 B; n = 50,000 synthetic unit vectors (1,024 dimensions: 2,049 / 1,027 B in Vortex) | 1,024 B (fp16 blob blocks) | measured; synthetic values, because embeddings barely compress: a vector is a few hundred random mantissas, so only the exponent bits of fp16 have entropy to give (tessera's pcodec array takes 14 %, zstd 6 %, Vortex's own encoding none); the model takes Vortex as central and the best of the three as low |
| BM25 index bytes / text bytes | 0.378 (80 % subsample range 0.378 to 0.383); n = 2,919 works | 1.5 (XADR-SCITADEL-008 §8) | measured (positions on, whole papers, nothing stored, `en_stem`); **from the rerun `sizing83-r4b`**, whose fetched text mix (JATS route 541 of the 10,000 works) differs from that of the other text factors of this table (the first run, n = 3,378 works with text, JATS route 1,484), because Europe PMC answered fewer requests in the rerun; the ratio is of bytes of index to bytes of text, so a different route mix moves it only through the mix of the two text types |
| Metadata bytes per work, JSON / zstd Parquet / tessera | 3.88 KB / 0.49 KB (up to 0.49) / 0.38 KB (0.38 to 0.39); n = 6,246 | not sized | measured (Parquet at the sample's rows per file; tessera: the `works`, `authorships` and `citations` blocks of the table below, flat rows, the same kept fields) |
| Document-model tables per paper with text, tessera (elements, chunks, figures, and for every paper the JATS-only tables at the JATS rate) | 34.7 KB (34.5 to 35.1); n = 3,189 works with text, of them 1,021 JATS | the remainder of 164 to 214 KB per paper less vectors and text *(modelled)* | measured (S-015; table below), 80 % subset range |
| Lossless figure bytes per paper with text (JPEG XL; JPEGs transcoded, rasters at distance 0) | 1,091 (885 to 1,311) KB; median 167; p90 1,664; n = 3,189 (JATS route 2,043 KB, n = 1,021; PDF route 643 KB, n = 2,168) | 100 KB to 1 MB (document-model, estimate) | measured (S-015); native bytes 1,288 KB, so JPEG XL saves 15 % |
| Images and figures per paper with text | 24.0 embedded images or linked graphics, of which 6.2 figures (an image, not a mask, of at least 64 px a side); JATS route 6.1 / 3.2, PDF route 32.4 / 7.6; n = 3,189 | 14.3 figures per paper (100 million over 7 million papers) | measured (S-015: `pdfimages -list`, poppler 26.11.0; PMC open-data graphics listing) |
| Embedded image bytes / PDF bytes, PDF route | 65.8 %; n = 2,168 PDFs | not split out | measured (S-015) |
| Cited works per paper (graph cache, 8 B per edge) | 27.2 (26.4 to 28); n = 6,246 | 20 to 30 GB for the graph | measured; the modelled size is kept as a floor |
| Bulk snapshots per generation | OpenAlex 0.76 TB jsonl (704 GiB), 0.80 TB Parquet (2026-10-14, manifest byte counts); Crossref 208 GB (2026 public data file); DataCite 33 GiB (2025 file); 1.05 / 1.05 / 1.09 TB per generation with the unmeasured sources | 0.4 / 0.5 / 0.8 TB | measured (manifest and published sizes) |
| OpenAlex delta between generations (partitions with `updated_date` on or after the previous release) | since 2026-09-23 (the release before): 512 GB of 756 GB jsonl (67.7 %); since 2026-07-15 (a quarter earlier): **686 GB (90.8 % jsonl)**, 728 GB (90.9 %) Parquet; since 2026-06-25: 93.2 %; 401 partitions | whole generations | measured (S-015; S3 listing of `data/jsonl` and `data/parquet`; only the current release is in the bucket, so the previous one is read off the dates, below) |

**Bytes per paper per table (S-015; tessera `.tsra` against Parquet zstd and the raw Arrow bytes; each table is one block for the whole sample).** n is the works that carry the table: every work for the metadata blocks, the works with text for the document blocks, the JATS works with text for the three JATS-only blocks (table cells, inline references, bibliography). Against the 37 KB of uncompressed text of S-013 (38.1 KB per paper with text): `elements.text` is 26.2 KB in tessera against 13.7 KB in Parquet zstd and 40.1 KB raw, so tessera is **1.9 times Parquet zstd on text**: its normalised codec set excludes Vortex's zstd encoding (vig-os/tessera#628), and strings are dictionary and FSST coded only. On numeric tables (`citations`) it is smaller than Parquet zstd.

| Table | n (works) | Rows per work | tessera B per work | Parquet zstd B | raw B | tessera / Parquet |
|---|---|---|---|---|---|---|
| `works` | 6,246 | 1.0 | 172 | 130 | 361 | 1.32 |
| `authorships` | 6,246 | 4.1 | 94 | 89 | 188 | 1.06 |
| `citations` | 6,246 | 27.2 | 119 | 163 | 436 | 0.73 |
| `elements` | 3,189 | 214.2 | 28,479 | 16,380 | 50,137 | 1.74 |
| `elements.text` (the column alone, inside `elements`) | 3,189 | 214.2 | 26,229 | 13,740 | 40,087 | 1.91 |
| `chunks` | 3,189 | 37.0 | 200 | 146 | 814 | 1.37 |
| `figures` | 3,189 | 6.3 | 54 | 42 | 321 | 1.28 |
| `table_cells` | 1,021 | 185.9 | 2,275 | 1,330 | 7,665 | 1.71 |
| `inline_refs` | 1,021 | 94.5 | 918 | 588 | 4,010 | 1.56 |
| `bib` | 1,021 | 52.8 | 2,810 | 1,594 | 5,980 | 1.76 |
| **Metadata per work, as the model takes it** | 6,246 | | **385** | **382** | **984** | **1.01** |
| **Document tables per paper with text, as the model takes it** (the JATS-only tables at their JATS rate for every paper) | 3,189 | | **34,734** | **20,080** | **68,928** | **1.73** |

Per paper, as the model takes it: **metadata 385 B per work** (`works`, `authorships`, `citations`), **document tables 34,734 B per paper with text** (of which `elements.text` 26,229 B, the hot chunk text), the JATS-only tables counted for every paper with text at their JATS rate (6,002 B), because PDF-route works need the T1 tier for them (#84). The PDF route has 2,168 works and the `elements` of a PDF carry page and box from `pdftotext -bbox-layout` (214 elements per paper with text against fewer, longer JATS paragraphs); a JATS element carries a zero page and box, which the encoder stores at no cost. Vectors, per chunk or figure ([bytes per vector](#24-size-model-measured-on-a-sample-s-013), factor table): a text chunk is one vector of 512 dimensions, 35.8 per paper with text.

**Figures by route (S-015, per work with text).** JATS route (1,021 works): 2.18 MB of linked graphics, 2.04 MB after JPEG XL, 6.1 graphics, 3.2 `<fig>`. PDF route (2,168 works): 0.84 MB of embedded images (65.8 % of the PDF bytes), 0.64 MB after JPEG XL, 32.4 images, 7.6 figures. 65,011 images were encoded with `cjxl` and 11,521 (JPEG 2000, JBIG2, CCITT, TIFF) stay as they are. Vector graphics in a PDF (SVG, DES-037) are not measured: `pdfimages` does not see them. The JATS figure bytes are the files PMC holds for the article: full-size journal JPEGs, 356 KB each, JPEG XL saves 6 % of them. 7 works' graphics listings failed and count as no figure bytes.

*Limits of the measurement.* (1) Works with only a landing page (25.4 % of the scholarly types) carry metadata only until their publisher-HTML route is measured (#86): text, chunks, vectors, the BM25 text, the document tables and the figure blobs apply to the covered 74.6 % of the works; low takes the least coverage. (2) `pdftotext` keeps running headers, references and table text that JATS body text drops, so the pdftotext route overstates text, chunks and BM25 bytes against a body-only extraction; the planning case is biased upward by that, by at most the difference between the two routes above. (3) T1 text is proxied by `pdftotext` (for the PDF route its blocks and their boxes by `pdftotext -bbox-layout`); the layout model's boxes, OCR and the T2 to T4 outputs are modelled (#84), and so are the table cells, inline references and bibliography of a PDF-route work, which are counted at the JATS-route rate until T1 produces them. Not in the model at all, because nothing measures or sizes them: SVG figures, page-region embeddings and vision-tier descriptions (generated lazily for the hot set, DES-037). (4) The Parquet figure is one file of the sample's rows; a file of tens of millions of rows has more distinct values, so it is a lower bound, and a few GB beside the vectors moves no total. (5) Patent XML and drawing bytes are not measured: the USPTO Open Data Portal answers `HTTP 401` without a key (#85). (6) TEI is modelled (the OpenAlex content API was not used). (7) The BM25 index is built with term positions over whole papers (tantivy-py's default `index_option='position'`, set explicitly), and its range is that of ten random 80 % subsamples, not a CI: resampling with replacement duplicates documents and shrinks the ratio. (8) The Parquet CI is the 1,000-round bootstrap of the other factors, but a resample repeats rows and a file of repeated rows compresses better, so the bootstrap interval lies below the mean; it is widened to include the mean, so the high case never sits below the central one. (9) The vectors are synthetic (a size depends on the entropy of the values, not on what they mean), and the figure term rests on the 3,189 works with text of one fetch of the sample, whose route mix differs from S-013's (above). (10) The tessera range is that of ten random 80 % subsets of the works, not a CI, for the reason of limit (7); the figure factors have bootstrap CIs. (11) Tessera bytes are one block per table for the whole sample: smaller blocks pay more for dictionaries, and a shard of 1 to 10 GB holds many papers, so a table of a few thousand rows is the conservative case. (12) The OpenAlex delta is the partitions changed since the previous release, an upper bound on the rows whose kept fields changed: `updated_date` moves for any field (a citation count included), and the previous release itself is not listable, so no row-level comparison was possible.

**B** is one generation of sealed products with its embeddings (a base with its deltas folded in), for the 23.2 million scholarly types: low 16.9 TB, central 21.3 TB, high 26.8 TB, measured in tessera blocks (S-015; the previous round, which modelled the figure, table and layout columns, gave 5.9 TB). Its parts, low / central / high: **figure blobs** 15.12 / 18.93 / 23.05 TB (measured: 1,091 KB of JPEG XL per paper with text × the covered works; it is 89 % of B); text vectors 0.53 / 0.64 / 1.33 TB (measured chunks × 512 dimensions × 2 bytes × the measured encoded-to-raw ratio 1.000 of Vortex, 1,024 dimensions in the high case); figure vectors 0.09 / 0.11 / 0.24 TB (6.2 measured figures per paper with text, same vector); the document tables 0.59 / 0.60 / 0.62 TB (measured, tessera: elements with their text, chunks, figure rows, table cells, inline references and bibliography; the text column is 0.45 TB of it); metadata 9 / 9 / 9 GB (measured, tessera); and the patent part, which is *modelled* (drawings 0.5 / 1.0 / 1.5 TB, vectors and text; #85). There is no modelled remainder any more: the old one (the figure, table and layout columns, 164 to 214 KB per paper) was 3.7 TB in the central case, 20 % of the measured figure bytes alone. The vectors of a work with only a landing page, and its document tables, apply to the covered works (74.6 % in the central case); the metadata applies to every work. At the first model's own scope of 7 million papers the same factors give B = 7.2 TB (first model 2.85 TB), R = 10.9 TB (6.7), warm 25.9 TB steady and 33.0 TB at the peak (12.7 and 15.5) and hot 0.6 and 1.2 TB (1.0 and 1.8): vectors, text and indexes were modelled well, the figures (the part this round measures), the raw PDFs and the bulk snapshots were not. **The figure bytes are the finding.** They are 1.09 MB per paper with text, against the 100 KB to 1 MB that the document model estimated, and the JATS route carries most of them (2.0 MB: PMC holds the full-size journal JPEGs, where a PDF-route paper's figures are the copies embedded in its PDF, 0.6 MB). Storing the figures losslessly is 89 % of B and what sets the size of the warm tier. **Embedding time.** The throughput target is the requirement SYS-050 (at least 5,000,000 chunks per GPU-hour, reported as OUT-004); this section derives the time from it, in one direction only: the planning case's 621 million chunks (covered works), counting text chunks only, take 124.2 GPU-hours at that floor, **5.18 GPU-days**, and a system that meets the requirement takes no more than that (2.6 at twice the floor).

**R** is everything kept under the raw-retention rule of XADR-SCITADEL-008 §12 (owner decision 2026-11-11): every raw input and every cascade tier's intermediate output. Nothing in it is deleted automatically.

| Kept class | Low (TB) | Central (TB) | High (TB) | Basis |
|---|---|---|---|---|
| Open-access PDFs of PDF-only works | 8.3 | 14.7 | 15.5 | measured: 52.1 % PDF-only × 1.21 MB, n = 6,246; unfetched PDFs imputed |
| JATS, TEI and USPTO XML (zstd) | 0.2 | 0.3 | 0.3 | JATS measured (5.9 KB per paper, n = 6,246); TEI 4.5 KB per PDF-only work and patent XML 0.05, 0.1, 0.15 TB *modelled* |
| Bulk snapshots, one full OpenAlex generation and three deltas, four generations of the rest | 4.0 | 4.0 | 4.2 | measured: the hub keeps the **whole** OpenAlex snapshot it bootstraps from (owner, 2026-11-22: the corpus starts from the keyless S3 snapshot, the API covers deltas only, SYS-003), plus Crossref and DataCite. S-015 measured the delta between generations: a quarterly generation is the partitions updated since the previous one (0.69 TB of 0.76 TB jsonl, 0.73 of 0.80 Parquet, 90.8 %), so the class is one full generation plus three deltas, 4.0 TB, not four full ones (4.2 TB): **deduplication between generations saves 0.21 TB, 5 % of the class**, because OpenAlex touches most records every quarter. The Crossref and DataCite files are yearly and unpartitioned, so every generation keeps them whole (0.29 TB with the unmeasured sources *modelled* at 0.05 TB); no PatentRef snapshot ([C-004 ruling](https://github.com/nerdmachines/scitadel-hub/issues/22#issuecomment-6995799805)) |
| Raw patent drawings | 0.5 | 1.0 | 2.0 | *modelled* (the USPTO Open Data Portal needs an API key, #85) |
| Cascade T1 to T4 outputs | 2.2 | 3.8 | 6.7 | *modelled*: 0.18, 0.30, 0.50 MB per processed PDF × the measured PDF-only count, plus 0.1, 0.2, 0.5 TB for the patent cascade (#84) |
| **R** | **15.2** | **23.8** | **28.7** | R / B = 0.90, 1.11, 1.07 |

**What snapshot deduplication needs.** Every input is still kept (SYS-014): this changes the accounting of the class, not the rule. The bucket holds only the current release (every object is dated 2026-10-14; `legacy-data/` is the retired pre-2025 layout, and the previous release is not listable), so the delta is computed from the `updated_date=` partitions: a record is in the partition of its last change, and the partitions dated on or after the previous release hold exactly the records new or changed since it. The release before this one (2026-09-23, 21 days earlier) already differs in 67.7 % of the bytes, a quarter earlier in 90.8 %: **partition-level deltas dedupe a quarter by only 9 %**, because OpenAlex re-stamps most records each quarter (a citation count is enough). Row-level deduplication would compare the kept fields of a row, not its stamp, and could keep only the rows whose content changed; it needs, in tessera, **keyed delta products over a base with a newest-row-wins read and tombstones** (vig-os/tessera#781, already filed: its upsert path is the mechanism), **a diff-ingest of a full generation against the sealed base** that emits only the rows whose kept fields changed, by a content hash, and a tombstone for every row that left (vig-os/tessera#952, filed with this measurement), and **retention classes that let a superseded base be reclaimed** (#906). The measurement above is the upper bound of what such a delta holds; the lower bound needs two listable releases and is a follow-up for the first quarterly update after the stage-0 slice (SYS-044).

**Not in R: the JATS graphics.** The figure files of a JATS-route article (2.18 MB per work, n = 1,021) are raw inputs of the article that SYS-014 keeps, but no class above holds them: R keeps the JATS XML and the PDFs of the PDF route. Their JPEG XL transcode in B reconstructs the original JPEG bit-exactly (DES-037), so B can stand for the keep copy; if the raw store must hold the files as fetched, R grows by about **11 TB** (23.2 million × 22.5 % JATS × that size) and the warm tier by the same. This is a decision for the owner, not a measurement; the numbers of this section leave it out.

**Warm tier (20+ TB of HDD attached to anvil, behind the `gerchowl/g-fleet#1363` versitygw/ZFS store; owner, 2026-11-18).** Holds R and the product history: the current and the previous base with their deltas, 2.1 B at steady state (the default retention of SYS-017). At the quarterly compaction the candidate base is added: current, previous and candidate, **3.1 B at the peak**. After the promotion the retention role deletes the old previous base; while snapshots still pin it, it occupies the same space it did before, so the peak stays 3.1 B (the first draft counted the pinned base on top, 4.1 B, which double-counted it). R is append-only, so snapshots pin nothing in it.

*Warm snapshot policy (proposed for `gerchowl/g-fleet#1363`).* Product generations and the raw store sit in two datasets. The products dataset takes daily sanoid snapshots kept 3 days: an undo window for a mistaken deletion, while the long history of products is the cold mirror's (section 6). The raw dataset takes daily snapshots kept 14 days and 4 weeks. A retired base is therefore freed at most 3 days after the retention role deletes it. The peak would reach 4.1 B only if a second candidate were built inside those 3 days (a QC retry right after a promotion); the scheduler waits for the pin to expire instead, which it can compute from the snapshot schedule (SYS-073, TEST-093).

| Warm tier (scholarly types) | Low | Central | High |
|---|---|---|---|
| R | 15.2 TB | 23.8 TB | 28.7 TB |
| Products, steady state (2.1 B) | 35.4 TB | 44.8 TB | 56.3 TB |
| **Steady total** | **50.7 TB (253 % of 20 TB)** | **68.6 TB (343 %)** | **85.0 TB (425 %)** |
| Products, compaction peak (3.1 B) | 52.3 TB | 66.1 TB | 83.1 TB |
| **Peak total** | **67.5 TB (338 %)** | **89.9 TB (450 %)** | **112 TB (559 %)** |

At the measured scope **no case fits 20 TB usable**: even the low case peaks at 338 % of it. **The capacity to ask for (O-13) is the planning case's warm peak divided by 0.8: 112 TB usable** (140 TB in the high case, 97 TB for the articles alone, 123 TB for all types; 41 TB at the first model's 7 million papers; the previous round's 53 TB had a modelled remainder where this one has the measured figures). **Usable is not raw:** a six-disk raidz2 needs about 169 TB raw for 112 TB usable and a mirror 225 TB, before ZFS overhead. The figure blobs are 65 % of the central peak; whether the warm tier keeps them losslessly, as DES-037 says, or the owner trades some of them for the lossless-only rule is the lever on this number, and 31.2 TB is the peak without any figure blob. Renders and crops are derived and are not on the warm tier.

**Cold** holds R plus every product generation its retention still references, so it is larger than warm, not a one-to-one copy. With the restic retention of section 6 (14 daily, 8 weekly, 12 monthly) every quarterly base that was live within the last 12 months stays referenced, about 6 B at a compaction: low 116 TB, central 152 TB, high 190 TB. A shorter retention for the product prefixes (for example 14 daily and 8 weekly, about R + 4 B) brings the central case to about 109 TB. Both counts include rejected candidates, which are written to `keep` first and stay referenced for up to 12 months ([C-006 ruling](https://github.com/nerdmachines/scitadel-hub/issues/25#issuecomment-6995800535)). The retention and the box size are chosen together in O-9 (`gerchowl/g-fleet#1649`).

**Stage 0 on the KC3000, before the warm tier exists.** Everything is on the one pool, so the need is: `products` 2.1 B (current plus compaction candidate, deltas of both), `index` two index generations during a rebuild (each 0.013 B of the paper part, measured below, plus the patent subset's), `keep` 3.1 B (the current base, the candidate written there first, SYS-059, and a retired base still pinned by the soak and by `keep`'s snapshots, plus deltas) **plus** the raw budget R₀ = 0.91 B of the paper part plus the patent subset's raw items **plus** 20 GiB for fixtures and the crops of confirmed reports and 35 GiB for the `state` dumps (below), and the fixed volumes `staging` 150, `state` 20, `gpu-io` 100, `scratch` 50, `runs` 150 and `research` 20 (490 GiB). With the slice's B = 205 GiB, of which 10 GiB is the patent subset (below), that is 1,262 GiB + 545 GiB. **Fixed-size and patent-scoped items do not scale with the slice.** The ratios are those of the paper part: R₀ per paper B is R without the bulk snapshots and the patent items (0.91 B), and the index ratio leaves out the modelled graph floor (the slice's adjacency cache is derived from the slice's own edges) and the patent BM25. **Patents in the slice.** The patent constants of the model (drawings 1.0 TB, vectors and text 0.05 TB in B; patent XML, raw drawings and the patent T1 to T4 outputs 1.3 TB in R) are sized for the whole patent set and are *modelled* until the USPTO key of #85 lands. The slice carries a **fixed patent subset: 1 % of the modelled patent set, about 13 weeks of grants** (its sizes are 1 % of the constants: 9.8 GiB in B, 12.1 GiB in R₀, 0.44 GiB of BM25 per generation), not a share of the paper slice; #85 replaces them with the measured weeks. The full OpenAlex snapshot generation is 704 GiB of jsonl, more than the whole raw budget R₀ = 195 GiB, so the slice holds **the rows of its works extracted from the snapshot** (the sample's 3.9 KB of metadata per work, about 0.9 GiB for the slice's 240 thousand papers) and not the snapshot; the whole snapshot is kept once the warm tier exists (section 5).

*Why one index generation is about 0.015 B (measured).* XADR-SCITADEL-008 §8 sizes indexes at "about 1.5× the text they cover", and the first model took 0.2 B per generation from that. The measured BM25 index (tantivy, positions, nothing stored) is **0.38× the text it covers** and the text is 38 KB per covered paper, so BM25 is 297 GB for the planning case. The IVF-flat index holds postings only, about 16 bytes per vector, and reads the vectors from the products (SYS-019, DES-006; whether a local list-ordered vector copy is needed is S-001): 12 GB for 621 million chunks and 108 million figures. The graph adjacency cache is 25 GB (the modelled 20 to 30 GB is its floor) and the optional HNSW cache is 30 GB in the high case only. One generation is 0.31, 0.33 and 0.39 TB. The slice takes the same share of every source, so the ratio holds for it. The first index build of the slice measures it again (SYS-044); if it comes out above 8 GiB for two generations, the `index` quota is re-applied from the measurement (O-2) before a second generation is built, because a rebuild needs room for two.

*Why `keep` holds 3.1 B (re-checked).* A retired base stays on disk for up to about 5 weeks after the promotion that retired it: the 7-day soak, then up to 4 weeks pinned by `keep`'s snapshots (daily ones kept 14 days, weekly ones 4 weeks). At a regular quarterly compaction that pin has expired, so `keep` holds only the current base and the candidate, 2.1 B. It reaches 3.1 B when a candidate is built while a retired base is still pinned: a QC retry, a re-derive under SYS-069 or a rollback within 5 weeks of a promotion. The quota keeps the 3.1 B so that those cases pause nothing; a second candidate on top of a still pinned retired base would need 4.1 B and waits for the pin to expire (SYS-073).

*`state` dumps (bounded).* The hub writes one zstd-compressed `.backup` dump per night to `keep/state-dumps/<UTC date>`, keeps the newest 7, and its retention role deletes older ones as an audited action (section 4). A deleted dump stays pinned by `keep`'s snapshots for up to 35 days, so at most 35 dumps are charged to `keep` at any time, bounded by the snapshot policy rather than by the live count. At ≤ 1 GiB per dump *(estimate; the stage-0 ledgers are far below the 20 GiB `state` quota and compress well)* that is 35 GiB. A dump larger than 1 GiB raises an alert, which is the signal to raise the line and the quota together. The long history of dumps lives in the restic repository, not in `keep`.

| Case | B (GiB) | Need (GiB) | Fits in 1,840 GiB |
|---|---|---|---|
| **Stage-0 slice** | 205 | 1,807 (5.2 B + 2 index generations + R₀ + 545) | **yes**, with 33 GiB of headroom |
| §8 initial demo (about 1 TB in total, working copies included) | about 50 | about 856 | yes |
| Phase 1 (scholarly types), low / central / high | 15,718 / 19,868 / 24,961 | 93,290 / 122,876 / 153,910 | no: more than the 3,819 GiB disk |
| After the warm tier exists (needs 2.11 B + 195 GiB) | at most 778 | 1,840 | the serving copy of phase 1 central (41.0 TiB) does not fit; the hot set of the split below does at its steady state |

**Consequence, stated plainly: phase 1 does not fit on the KC3000 pool.** Stage 0 therefore runs a **slice** of B ≤ 205 GiB, of which 10 GiB is the patent subset; the paper part, 195 GiB, is 1.03 % of the planning case's paper part (18,892 GiB; 0.83 to 1.28 % across the range), about 240 thousand works and 6.4 million of its 621 million chunks (the share is of the paper part, not of B with its patents, which would overstate it). The slice is a manifest pinned in the run record (SYS-057): the same share of every paper source, chosen with a fixed seed, plus the fixed patent subset above, so that it is representative and reproducible. **The quotas of section 2.1 follow from the table above:** `products` 2.1 × 205 = 430.5 → 435; `index` 2 × (0.013 × 195 + 0.44) = 6.0 → 10; `keep` 3.1 × 205 + R₀ (195) + 20 + 35 = 886, plus 20 GiB of headroom (what the rounding of the other quotas leaves of the 1,840) → 905, so that the nightly dumps and a fixture write never reach `EDQUOT` and pause ingest; the fixed volumes as listed; the nine limits still sum to 1,840 GiB. Applying them on anvil is the owner's O-2 (re-apply the script of section 2.2). When the warm tier exists, the canonical copy, R and the history move to it by the checksum-verified copy of SYS-015 and the KC3000 holds the serving copy, so B can grow to about 778 GiB; the full phase-1 serving copy needs stage-1 NVMe or another disk (O-14, `gerchowl/g-fleet#1650`), or the hot/warm split below.

**Hot/warm split.** Hot (NVMe) = text vectors and figure vectors + chunk text + indexes (BM25, IVF postings, graph cache) + metadata; warm (HDD) = everything else: raw inputs R, the figure, table, layout and drawing columns, and the product history. Hot steady = the current base's hot columns with its deltas (1.1 ×) + one index generation; hot peak = the same plus the candidate's hot columns (1.0 ×) and the second index generation of a rebuild.

| Case (scholarly types) | Hot steady | Hot peak | Warm, everything else, steady | Warm, everything else, peak | Warm with the hot columns kept canonical (above), steady / peak |
|---|---|---|---|---|---|
| Low | 1.5 TB (1,424 GiB) | 2.9 TB (2,744 GiB) | 48.3 TB | 64.1 TB | 50.7 / 67.5 TB |
| Central | 1.7 TB (1,600 GiB) | 3.3 TB (3,083 GiB) | 65.9 TB | 86.0 TB | 68.6 / 89.9 TB |
| High | 2.7 TB (2,514 GiB) | 5.2 TB (4,833 GiB) | 80.6 TB | 105 TB | 85.0 / 112 TB |

Planning case, hot set, steady: text vectors 0.7 TB, figure vectors 0.1 TB, chunk text 0.5 TB (the text column of the measured elements block, tessera), metadata 10 GB, indexes 0.33 TB (BM25 297 GB). Against the first model's about 1.0 TB steady and 1.8 TB peak the split is 1.7 and 3.3 TB for the scholarly types (0.6 and 1.2 TB at 7 million papers), against a full serving copy of 45.1 TB. The figure blobs are warm only (they are not in the hot set), so the measured figures moved the warm tier and left the hot one where it was.

- **O-14 (`gerchowl/g-fleet#1650`, hot NVMe).** The KC3000 pool has about 2.7 TiB free (section 1). The planning case needs 1.6 TiB steady and 3.0 TiB at the compaction peak (high case 4.7 TiB): the steady state fits, the peak does not fit. The full serving copy never fits. The split turns O-14 from the full serving copy into the hot peak of the planning case.
- **O-13 (`gerchowl/g-fleet#1363`, warm HDD).** The split moves the hot columns out of warm only if their canonical copy leaves it, which SYS-015 and SYS-072 do not allow (the canonical copy is the warm one and the hot copy a mirror). With the canonical copy kept warm, O-13 is the usable ask above. If the canonical copy of the hot columns were NVMe-resident, warm would need 86.0 TB at the peak (108 TB usable).
- **int8 vectors** (one byte per dimension plus a 4-byte scale per vector; measured at 0.998 of raw in Vortex, so no further saving from encoding) halve the vector bytes: hot steady 1.3 TB and hot peak 2.5 TB for the planning case (2.3 TiB; vectors 0.8 → 0.4 TB). The peak then needs 85 % of the 2.7 TiB. Its recall cost is not measured here; it is deferred to the SYS-065 benchmark.
- **S-001 (#17).** The split makes the local, list-ordered copy of the vectors under `index/ann/` a requirement of the hub, not an open option: the vectors are the largest hot column and the IVF index reads them by posting list from NVMe, so they sit on the hot tier by construction. #17 stays open for the recall and latency question.

**Corpus ingest waits for the off-anvil copy.** The stage-0 slice is the first raw data the hub keeps, and until the warm tier exists its only other copy is the cold mirror. Ingest beyond the CC0 fixture corpus therefore starts only after the first restic backup of `keep` and a passed restore from cold (SYS-072, O-9).

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
- Serving holds no GPU device (SYS-024). The **query embedder** (SYS-071) runs on CPU inside `vm-hub` by default, with the same model, revision, quantization and weights hash as the index generation it queries; its weights come through the signed manifest (SYS-056) into `staging/models/`. A reserved GPU slot is possible only by a service definition naming a GPU executor outside `vm-hub`, after the benchmark of TEST-091 on the 5090 shows the CPU path cannot meet its budget, and with the owner's approval.

### 3.1 Other compute hosts

- **ksb (SYS-063).** Nothing reaches ksb implicitly. The hub builds a named slice `ksb-slice-<id>` from the stage-0 slice (a manifest of paths, sizes and blake3 hashes plus the files; CC0, CC-BY and public-domain content only), transfers it by the mechanism of g-fleet docs/ksb-compute.md, the task verifies it against the manifest on arrival, reads it read-only and deletes it at the end. The tests that need the stage-0 corpus on ksb (TEST-021, TEST-029, TEST-030, TEST-038, TEST-041, TEST-042, TEST-084) use this slice, and TEST-053 uses a 50,000-paper subset built from it. A ksb task has no network path to `vm-hub` or vm-storage: a test that needs the live stage-0 hub, the gateway or the backup set (TEST-035, TEST-049, TEST-050, TEST-066) runs in `anvil-microvm` instead. Ksb's capacity for a slice of up to 250 GiB is owner action O-15 (`gerchowl/g-fleet#654` requires an explicit transfer).
- **sage (SYS-070), only if an overflow definition targets sage.** With no enabled service definition naming sage there is no data path and no credential. If one is enabled, the hand-off payload sits under its own prefix of `scitadel-hub-runs`, the T3-worker role (section 4) fetches it with short-lived credentials, the result comes back under the same prefix with a manifest and is accepted under SYS-062, and nothing stays on sage afterwards. The network path from sage to vm-storage is owner action O-16.
- **Service definitions are configuration.** Moving a tier from one executor to another is a new version of its definition in the service registry (SYS-067, SYS-069), with no code change; every run and every row records the definition hash (SYS-068).

**Decision gate G-2 (random-read latency through virtiofs).** The indexes are read by memory-mapped random access, and a guest reads them through virtiofs. SYS-012 measures p95 4 KiB random read through that path. If it exceeds 1 ms *(estimate)*, the `index` subvolume is not shared but holds a sparse raw ext4 image attached to `vm-hub` as a virtio block device, the way vm-dev's images are attached; the quota then caps the image file. The gate is decided by the measurement, not by preference, and the rest of the layout is unaffected.

## 4. Buckets (g-fleet#1449 tiers)

`gerchowl/g-fleet#1449` (owner go 2026-11-09) provides, per project, `<project>-scratch` (48 h), `<project>-runs` (28 d, a warning at 72 h or less remaining), `<project>-keep` (no expiry) and `<project>-research` (indefinite, versioned, write-once when finished). For the project `scitadel-hub`:

| Bucket | Tier meaning | What the hub puts there |
|---|---|---|
| `scitadel-hub-scratch` | 48 h | tenant-simulation staging and temporary copies that can be rebuilt within 48 h. **No queued work and no quarantine**: a weekend must not expire either |
| `scitadel-hub-runs` | 28 d | run manifests, QC and golden-set diff reports, embedding-drift reports (reports only: candidate products are in `keep`, SYS-059, [C-006 ruling](https://github.com/nerdmachines/scitadel-hub/issues/25#issuecomment-6995800535)), copies of job logs, **quarantined inputs awaiting triage** and **cascade hand-off payloads** (T3 and T4 work waiting for budget), whose lifetime of weeks matches this tier |
| `scitadel-hub-keep` | no expiry; products are deleted only by the retention role | the **canonical sealed products** and their generations (`base/<release>/`, `delta/<date>.tsra`, `current`); the **content-addressed raw and intermediate store** (blake3 keys): open-access PDFs, JATS, TEI and USPTO XML, bulk snapshots, T1 to T4 outputs keyed by input hash, tool, model, version and definition hash; the **service definitions** by hash (SYS-067); the private golden fixtures (the non-CC fixture bucket of XADR-SCITADEL-008 §13) with the crops of confirmed reports; unresolved quarantine items (`quarantine/`); nightly `state` dumps under `state-dumps/`, the newest 7 (section 2.4) |
| `scitadel-hub-research` | versioned, write-once when finished | finished evaluation results only: grounding-benchmark runs on a pinned release, golden-set baselines |

**Expiry behaviour and alerts.** `scratch` and `runs` objects are copies, never the only record: the queue position, the quarantine decision and the budget spend live in the run ledger in `state` (SYS-057), and the payload copies data whose original is kept (SYS-014). The `runs` tier warns at 72 h or less before expiry (SYS-013); the warning raises an alert naming the run and the items. A **queued item whose payload expired is not skipped**: the orchestrator rebuilds the payload from the kept original and puts it again, which starts a new 28-day clock (SYS-006). A **quarantined item still untriaged at the warning** is copied by the hub into `keep/quarantine/`, so the decision outlives the bucket, and the alert says so; a confirmed error becomes a red fixture in `keep`. Hand-off payloads that carry PDF pages are removed by the hub when the run is accepted; expiry is only the backstop.

**Why the corpus is in `keep`, not `research`.** XADR-SCITADEL-008 §2 retires generations by an explicit retention policy (the last two bases and their deltas), while `research` is write-once and indefinite. The two rules meet in `gerchowl/g-fleet#1363` (H6), per the same section. Until that is settled the corpus generations live in `keep`, where one dedicated role may delete a retired generation by policy and nothing else may delete at all (SYS-017). `research` holds only data that is meant to be immutable.

**Roles (gateway accounts and permissions).** Each cell is what the role may do; "create" means a new key and never an overwrite.

| Role | scratch | runs | keep | research |
|---|---|---|---|---|
| hub serving | none | read | read | read |
| hub ingest and promotion | read, write | read, write | create; overwrite **only** the `current` pointer key | create once |
| hub retention (the only automatic deleter) | none | none | delete keys of a retired or rejected product generation, after the soak of SYS-060, and `state-dumps/` older than the newest 7; **never** raw inputs or intermediates | none |
| operator hand-drop (`hub raw drop`, `RawDrop::drop_refetchable`) | none | none | delete one re-fetchable open-access PDF under `cas/` whose hash and URL are recorded, audited in the ledger before the delete (SYS-014); refused for every other class | none |
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
| Internal Parquet staging, until tessera wave 1 of #778 lands | `staging/parquet/` | never published and never in a bucket (XADR-SCITADEL-008 §2); a parse of kept raw inputs, so not kept itself; the path is dropped with wave 1 ([C-002 ruling](https://github.com/nerdmachines/scitadel-hub/issues/20#issuecomment-6995799107)) | yes, from the kept raw inputs | no |
| Raw inputs, **all** of them: open-access PDFs, JATS, TEI, USPTO XML, bulk snapshots | `scitadel-hub-keep`, artefact store (stage 0, budget R₀ of section 2.4); the warm tier later | content-addressed (blake3), never in a product, never deleted automatically (SYS-014); the hub never serves PDF bytes (D-007) | upstream may withdraw them | yes, mirrored cold |
| Cascade intermediates, T1 to T4 (OCR text, layout, math, vision-language and verdict output) | artefact store, keyed by input hash, tool, model, version and definition hash | kept so that a re-derive starts from the stored OCR and not from the GPU (SYS-066) | at GPU cost | yes, mirrored cold |
| Page renders and region crops | `staging/renders/` (hot), derived | rebuildable from the kept originals on demand (SYS-064); evicted least recently used first; only the crop of a confirmed report is kept, as a red fixture in `keep` | yes | no |
| Service definitions | the hub's configuration, each version also by hash in `keep` | versioned, immutable, resolvable from any ledger or provenance hash (SYS-067) | yes | via `keep` |
| `.tsra` products, hot serving copy | `products/<collection>/base|delta/…`, `current` | read locally by the query engine; written to `keep` first, then here (SYS-059) | yes, from `keep` | via `keep` |
| `.tsra` products, canonical copy | `scitadel-hub-keep` (stage 0), then the warm tier | the S3 store of record; the hot copy is a mirror of it | yes | yes |
| Embeddings (one product per model, beside each shard); image embeddings of figures and page regions form a product of their own (SYS-065) | `products/…/embeddings/<model>/` | row-aligned fp16 blob blocks inside `.tsra` until vig-os/tessera#768, then re-sealed bit-exact to native Vortex fixed-size lists, recorded in provenance ([C-001 ruling](https://github.com/nerdmachines/scitadel-hub/issues/19#issuecomment-6995798717)); the patent vectors at the constant of [section 2.4](#24-size-model-measured-on-a-sample-s-013) and about 51 GB for 50,000,000 chunks at 512 dimensions in fp16; at full phase 1 the text and figure vectors of the planning case of section 2.4 | yes (GPU cost) | via `keep` |
| BM25 and ANN indexes | `index/bm25/…`, `index/ann/…` | **local NVMe random access**, uncompressed, copy-on-write (SYS-012) | yes, ≤ 24 h *(estimate)* (SYS-021) | no |
| Graph: typed edge tables | `products/…/graph/` | tables are products | yes | via `keep` |
| Graph: adjacency (CSR) cache | `index/graph/` | derived cache | yes | no |
| Hub state: run ledger (SYS-057), subscriptions, credit and freshness ledgers, job and hash ledger, retention audit, metering counters | `state/` (SQLite, `+C`) | small, rewritten in place | partly (ledgers are not) | yes: hourly snapshots, nightly dump to `keep` (newest 7 kept there, history in restic) |
| GPU inputs, outputs, model weights | `gpu-io/{in/<run-id>,out/<run-id>,models}` | visible to `gpu_submit` at the project path; `in/` holds copies of kept data, removed within 24 h of acceptance (O-8); weights fetched at first run through a signed manifest, never baked into an image (SYS-056), and checked against the definition's weights hash (SYS-067) | yes | no |
| QC and diff reports about candidates, quarantined inputs, hand-off payloads | `scitadel-hub-runs` | 28-day working record; the run record itself is in the ledger (`state`) | yes | no |
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

**Image processing (SYS-064 to SYS-066).** The kept originals feed three things. Page renders and region crops are made on demand into `staging/renders/` and are derived and evictable: a report on a bad table is shown against its source region, the element is re-extracted from it, and only the crop of a confirmed report is kept, as a red fixture in `keep`. Image embeddings of figures and page regions (the model named by the service definition, SYS-067) run as GPU jobs under the same acceptance rules. A vision tier can be re-run on demand from the stored inputs, writing new intermediates beside the old. A crop shown to a reporting user is a licence-gated derived image; PDFs are never served.

## 6. Durability

In order of when each layer exists.

1. **Snapshots (btrfs, stage 0 now)**, SYS-045. They protect against accidental deletion and overwrite. They do **not** protect against loss of the KC3000, of anvil or of the LUKS key: a snapshot shares the disk with its source.
2. **Off-anvil encrypted backup (restic to a Hetzner Storage Box)**, SYS-046, SYS-016, SYS-072. **It is the only copy of the raw data outside anvil**, before and after the warm tier exists, and the keep-everything policy is gated on it (below). Nightly, client-side encrypted, keys only in the fleet's `sops`. The backup set is exactly the non-rebuildable data: `scitadel-hub-keep` (canonical products, raw inputs and intermediates), `scitadel-hub-research` and the `state` dumps, read from the newest read-only snapshot and not from the live gateway directory. Once the warm tier exists the cold tier mirrors it, holding more than warm because its retention keeps older product generations (section 2.4). Retention in the repository: 14 daily, 8 weekly, 12 monthly. A monthly `restic check --read-data-subset=5%`. The Storage Box does not accept `zfs receive`, which is why this layer is restic (or borg) and not block replication. It can start **before** the warm store exists, because it needs no ZFS, and it must: it is a gate for corpus ingest (owner action O-9, `gerchowl/g-fleet#1649`).
3. **Interim target (`gerchowl/g-fleet#1438`).** The fleet's decided interim backup is the vm-storage S3 on this same KC3000, separate from the 990 PRO. For hub data that already lives on the KC3000 it adds no failure domain, so it is not counted here. Research data follows the owner's refinement of `#1438`: a client-side-encrypted push to the separate fleet's target, with a restore drill and `restic check` before any research cutover.
4. **Migration to the warm store on anvil's HDDs (`gerchowl/g-fleet#1363`), once it exists.** The warm store is 20+ TB of HDD attached to anvil, ZFS (raidz2 or mirror, the owner's or g-fleet's call) behind its own versitygw (owner, 2026-11-18). The canonical bucket contents, with the raw inputs, the intermediates and the product history, move to it by a checksum-verified copy (`rclone copy --checksum`, then a listing and hash compare that must show 0 differences, SYS-015). Only after a restore from cold of the migrated set has passed (SYS-072) is the hub's S3 endpoint flipped by configuration, and the KC3000 buckets shrink to the hot working set. The warm store snapshots with sanoid (policy in section 2.4) and ships off-anvil with restic to the Storage Box (the same layer 2, now sourced from the warm store). ZFS redundancy covers a failed HDD; it does not add a failure domain.
5. **Restore drill, quarterly and before any keep or research cutover**, SYS-047: an empty microVM, the backup set, rebuilt indexes, the smoke suite and the golden queries, within 8 h *(estimate)* (OUT-017).

**One failure domain: anvil.** The hot tier (KC3000 NVMe) and the warm tier (the HDD pool) are different disks in the same host. A failed disk is covered (ZFS redundancy on warm; the canonical copy on warm for anything hot), but the loss of anvil (theft, fire, hardware damage), of its LUKS keys, or a host-level compromise takes both tiers at once. No second on-prem host is planned. The cold mirror on the Storage Box is therefore the **only off-anvil copy of the raw data**, and SYS-072 makes it a gate of the keep-everything policy of SYS-014 rather than a best effort:

- corpus ingest beyond the CC0 fixture corpus does not start until the first backup of `keep` has completed and a restore from cold has passed;
- the scheduler starts no new run that writes raw inputs or intermediates while the newest successful backup is older than 48 h *(estimate)*: ingest pauses with an alert and nothing is deleted;
- the warm cutover does not flip the endpoint until a restore from cold of the migrated set has passed;
- a monthly restore of a random sample of objects from cold, verified against the ledger's blake3 hashes, keeps the gate honest (TEST-092).

**What is and is not at risk before layer 2 exists.** Until the first off-box backup runs, hub data has a single failure domain. In phase 1 almost all of it is rebuildable from public upstreams. What is not: the content-API TEI (paid per fetch), the kept raw inputs and intermediates (re-fetchable only while upstream still serves them, and re-derivable only at GPU cost), the private golden fixtures, finished research results and the `state` ledgers. Until layer 2 and its first successful restore from cold exist, those are the reason not to start corpus ingest or cut over `keep` or `research` for real use (SYS-072, and the gate of `#1438`).

## 7. Owner actions

Nothing here has been changed on any host. Each item names the g-fleet issue that owns it; the issues for O-2, O-3, O-4, O-5, O-9 and O-14 were filed on 2026-11-18 with the action, the reason and a link back to this document.

| # | Action | Owner issue |
|---|---|---|
| O-1 | Decide whether stage-0 retention on the KC3000 is 1 base and its deltas plus the previous base for a 7-day soak after each promotion (proposed here, in SYS-017) rather than the default 2, until the warm tier exists. The quotas of section 2.4 hold the current, the candidate and the previous base in `keep`. | `gerchowl/g-fleet#1363` |
| O-2 | Enable simple quotas on the `anvil-vm` pool and apply the layout script of section 2.2 (subvolumes, attributes, limits) before the hub microVM first boots. | `gerchowl/g-fleet#1645` (related `#1474`) |
| O-3 | Install the btrbk policy of section 2.3 for the hub subvolumes. | `gerchowl/g-fleet#1646` (related `#1438`) |
| O-4 | Register the hub budget (1,840 GiB, nine limits) with the pool's fill watchdog and budget check. | `gerchowl/g-fleet#1647` (module `anvil-vm-pool.nix`) |
| O-5 | Add the bind mount of `gpu-io` at `/srv/anvil/projects/scitadel-hub` and check that `vm-dev` sees it through `anvil-projects`. | `gerchowl/g-fleet#1648` (related `#1402`) |
| O-6 | Provision `scitadel-hub-{scratch,runs,keep,research}` per tier. Fix the gateway root (proposed `/var/lib/microvms/data/s3`), make each hub bucket a btrfs subvolume (or adopt the pre-created ones), and verify per-key rules or versioning for the `current` pointer. | `gerchowl/g-fleet#1449` (depends on `#1377` for vm-storage's RAM slot) |
| O-7 | Define `vm-hub` (the hub as a microVM) with the five virtiofs shares of section 3, importing the private module without patching it; hub secrets in their own `sops` file. | `gerchowl/g-fleet#1474` (blocked on `nerdmachines/scitadel-hub-deploy#2`) |
| O-8 | Settle how the add-only rule for `/srv/anvil` meets the hub's removal of old `out/<run-id>/` directories and of its own `in/<run-id>/` copies, and how `research` meets corpus generations. | `gerchowl/g-fleet#1363` (H6 per XADR-SCITADEL-008 §2) |
| O-9 | **Gate for corpus ingest (SYS-072).** Provision the Hetzner Storage Box and the restic repository, keys only in `sops`, nightly job and monthly check, a first full backup and a restore from cold, before the hub ingests beyond its CC0 fixtures and before the warm store exists. It is the only off-anvil copy of the raw data. Pick the repository retention with the capacity: the cold figures of [section 2.4](#24-size-model-measured-on-a-sample-s-013) for the retention of section 6 and for a shorter product retention. | `gerchowl/g-fleet#1649` (related `#1263`, `#1363`, `#1438`) |
| O-10 | Interim backup target and the restore drill gate; research data to the separate fleet's target, client-side encrypted. | `gerchowl/g-fleet#1438` |
| O-11 | Build the warm tier on the 20+ TB of HDD attached to anvil (ZFS, raidz2 or mirror, versitygw, sanoid with the snapshot policy of section 2.4) and the checksum-verified migration, flipped only after a restore from cold (SYS-072). | `gerchowl/g-fleet#1363` |
| O-12 | Provide the observability seam the hub exports to (freshness, spend, queue, quota alerts). | `gerchowl/g-fleet#1474` (the `s3` seam of `modules/observability/interface.nix`) |
| O-13 | **Warm capacity and date.** The warm tier is 20+ TB of HDD attached to anvil (owner, 2026-11-18). Confirm its **usable** capacity after the ZFS layout (raidz2 or mirror, the owner's or g-fleet's call) and the date it becomes available, and check it against the planning case of section 2.4: the ask is its warm peak divided by 0.8, in usable TB (raw is larger by the layout's overhead, also derived there). The corpus scope behind the planning case is the S-014 ruling (#88). Cold capacity is O-9. | `gerchowl/g-fleet#1363` |
| O-14 | **Hot capacity for full phase 1.** The hot set of the planning case of section 2.4 (the hot/warm split: vectors, chunk text, indexes, metadata and graph cache) is what the NVMe must hold, steady and at the compaction peak; the full serving copy is larger still (the warm HDDs cannot serve memory-mapped random reads). Decide between the stage-1 AX local NVMe (XADR-SCITADEL-008 §8), an additional NVMe disk in anvil, and int8 vectors (SYS-065). | `gerchowl/g-fleet#1650` (related `gerchowl/g-fleet#1363`) |
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
| G-7 | Raw retention and capacity | Keep every raw input and intermediate; stage 0 within the raw budget R₀ of section 2.4, pause at 90 %, never delete; the stage-0 slice is the one of section 2.4 | O-13, O-14 |
| G-10 | Where the query embedder runs (owner, 2026-11-18: hub-side, `vig-os/scitadel#316`) | CPU in `vm-hub` by default; a reserved GPU slot only by service definition and owner approval; clients send text only | the benchmark of TEST-091 on the 5090 (owner) |
| G-9 | Hot and warm share anvil as one failure domain | No second on-prem host; the cold mirror is the only off-anvil copy and gates corpus ingest, raw-writing runs and the warm cutover (SYS-072) | O-9 |
| G-8 | Where T3 runs | The 5090 via `gpu_submit` by default; sage only as an optional overflow, by service definition | O-16 |
| G-5 | Add-only rule versus retention; `research` versus corpus | Corpus generations in `keep`; `out/` is never deleted until settled | `gerchowl/g-fleet#1363` (O-8) |
| G-6 | Guest uid mapping for the virtiofs shares | A module detail, not a layout fact | `nerdmachines/scitadel-hub-deploy#2` |

## 9. Stage 1: Hetzner, first hosted users

Tied to XADR-SCITADEL-008 §8, "Stage 1 — Hetzner".

- **Serving.** A Hetzner AX dedicated server runs the hub binary on CPU. The same directory names (`products`, `index`, `staging`, `state`) sit on its local NVMe with the same rules: indexes uncompressed and copy-on-write, `state` the only in-place volume. The AX file system is a choice of that host's module (not specified here); the contract is the rules, not btrfs.
- **Warm.** Hetzner Object Storage replaces the fleet's versitygw as the distribution point for `.tsra` products. The bucket names and tiers are unchanged (SYS-039), only the endpoint is. The raw inputs and intermediates stay on the warm ZFS pool attached to anvil, mirrored to the Storage Box.
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
| Object tiers | KC3000 buckets via vm-storage (`scratch`, `runs`, `keep` with raw and intermediates within its budget, `research`) | the warm ZFS pool on anvil's 20+ TB of HDD, via versitygw, holds raw, intermediates and product history; KC3000 keeps the serving copy; same host, one failure domain | Hetzner Object Storage | shared read-only distribution bucket, or the customer's S3 |
| Cold | restic to the Storage Box (O-9), the gate of corpus ingest (SYS-072) | restic from the warm store; the only off-anvil copy | unchanged | the administrator's choice on-prem |
