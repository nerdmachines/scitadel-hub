# L3: licensing and TDM

Licence classes on every row, the features that are designed but disabled in phase 1, privacy controls, and the licences of the parts. Source: XADR-SCITADEL-008 §12 (licence classes and the legal basis by tier), §15 (sequencing: build first, licence-clean) and §16 (licensing). The gate order and the paid-tier view are [DES-020](adapters-and-pool.md); this file adds the class model, the disabled paths and the release obligations.

> **Source legend.** As in [the tessera boundary](tessera-boundary.md). **Not legal advice**; every reading is to be verified with counsel before the first hosted user (owner actions are in the private repositories). **Read-path enforcement of withdrawn opt-outs** is the paid read gate of [the tessera boundary](tessera-boundary.md), section 1.2, under [the paid read rule](tessera-boundary.md#the-paid-read-rule) (DES-057, DES-058; D-010). DES-054 and DES-020 reference it. No commercial terms appear in this repository. Every DES below is `proposed`.

| DES | Title | Realises | Uses |
|---|---|---|---|
| DES-054 | Licence classes and the gated features of phase 1 | SYS-052, SYS-053, SYS-054, SYS-001 | DES-011, DES-020 |
| DES-055 | Privacy controls: erasure, bounded logs, no reading history | SYS-042 | DES-005, DES-054 |
| DES-056 | Licence per part, release hygiene and model-weight policy | SYS-056, SYS-026, SYS-030 | DES-035 |

## 1. Licence classes and gated features (DES-054)

Every row and every artefact carries a licence class column (SYS-052); the protocol carries it ([DES-033](protocol.md)).

| Class | Cache and index | Cascade up to | Served to |
|---|---|---|---|
| CC BY, CC0, public domain | yes | T4 | every tier; attribution kept on `search` and `get` |
| CC BY-NC | not in any paid hosted tier | none | excluded from paid tiers (D-006) |
| CC BY-ND | not in redistributed indexes | none | excluded from paid tiers until the law is clear (D-006) |
| Free to read, no licence | lab-internal | T3 | lab or research-organisation on-prem only |
| Paywalled, obtained with a member's access rights | entitled users only | T3 | entitled users only |

- **Phase 1 is licence-clean** (D-005): only CC0, CC BY and public-domain content per item, whose access terms allow bulk harvest; one class, `public-licence-clean`, is written and `get` and `search` cannot return a row outside it (SYS-053). The gating paths are wired through the schema and the protocol, so phase 2 is configuration, not a rewrite; no code path that reads caches or serves other content is enabled.
- **Designed but disabled:** entitlement classes (H4, vig-os/scitadel [#318](https://github.com/vig-os/scitadel/issues/318)); local display of licensed content for entitled lab users; COUNTER 5.1 and SUSHI reporting, whose recording path is a no-op while no licensed content is served.
- **Deferred until the ETH Library conversation:** bulk harvest of an institutional repository, CORE and S2ORC full text, unlicensed green and bronze full text, paywalled caches, EPO paid bulk and Swiss repository federation. Phase 2 licensed content goes into a separate, lab-internal class and never reopens the phase-1 surface.
- **Legal basis by tier.** Research organisations rely on scientific TDM exceptions (EU DSM Art. 3, Swiss CopA Art. 24d), which do not allow commercial redistribution of mining results; the commercial hosted tier relies on Art. 4 and so honours every machine-readable opt-out, re-checked on every re-ingest: gates 2, 3 and 6 of [DES-020](adapters-and-pool.md) (SYS-055, SYS-054). A flipped source or item opt-out is withdrawn from paid reads by [the paid read rule](tessera-boundary.md#the-paid-read-rule) (D-010; [DES-057](tessera-boundary.md)).
- **Database right.** OpenAlex's CC0 declaration waives it for its subsets; every product pins the upstream snapshot date for audit ([DES-023](data-model-and-lifecycle.md)).
- **Phase-1 sources** are listed by #323 and the ADR §15; each source is an `IngestAdapter` descriptor with its licence basis ([DES-018](adapters-and-pool.md)). Retraction flags are a must-have, joined at index build ([DES-026](retrieval.md)).

## 2. Privacy controls (DES-055)

- **Erasure** is honoured by soft-deleting from the index while retaining the hash for deduplication: an erasure tombstone in the delta ([DES-005](tessera-boundary.md)) excludes the subject at index build and in every response, within 30 days (SYS-042). Whether that suffices for sealed products and kept raw inputs is S-006.
- **Logging** is limited to entitlement checks, retained at most 30 days *(estimate)*; **no per-user reading history** is stored.
- **GDPR duties before the first hosted user** (a DPIA and an Art. 14 notice; legitimate-interest basis for ORCID and author data) are owner actions, not code. Research-analytics profiling is later and defaults to aggregates (XADR-SCITADEL-008 §18); no design here.

## 3. Licence per part, release hygiene and model weights (DES-056)

| Part | Licence |
|---|---|
| client and libraries | `MIT OR Apache-2.0` |
| hub server | `AGPL-3.0-only OR LicenseRef-scitadel-Commercial`, with written AGPL section 7 permissions for client and cloud interoperation (D-001) |
| `scitadel-hub-proto` | `MIT OR Apache-2.0`, in the client repository |
| protocol prose spec | Community Specification License 1.0 |
| conformance vectors and verifier | CC0-1.0, in a sibling repository |
| deploy packaging; control plane | proprietary, in private repositories |

- **Release train** (SYS-056): a NOTICE file generated with `cargo-about`; a CycloneDX JSON SBOM with every release; `cargo-deny` on the client tree with an allowlist and an explicit copyleft deny (`GPL`, `AGPL`, `LGPL`, `SSPL`, `BUSL`).
- **Model weights** are fetched at first run through a signed manifest and never baked into an OCI image; each is a service definition entry with its licence noted ([DES-015](tessera-boundary.md)). A weight whose licence carries a usage threshold is flagged for review before scale.
- **Contribution and trademark** are owner decisions recorded in the ADR (an Apache ICLA at the first external pull request); no code depends on them.

## 4. Verification

| Test | Verifies | Method | Pass criterion |
|---|---|---|---|
| TEST-148 | DES-054 | One fixture item of each class through ingest, search and `get` with every gated feature at its phase-1 setting, then with a test-only phase-2 class enabled | phase 1: 0 rows outside `public-licence-clean` returned; 0 NC or ND rows in any paid-tier view; the COUNTER path emits nothing; phase 2 by configuration alone returns the extra class to a lab-tier query only |
| TEST-149 | DES-055 | An erasure request for a fixture author, an access log with entitlement checks and a search by a fixture user | the author absent from every response within the bound; the hash retained for dedup; log entries expire at the retention bound; 0 reading-history rows |
| TEST-150 | DES-056 | A release dry run on the client tree with an injected GPL dependency; a build of the hub OCI image | `cargo-deny` fails the injected dependency; NOTICE and SBOM produced; 0 model weights in the image; the proto crate's `Cargo.toml` says `MIT OR Apache-2.0` |
