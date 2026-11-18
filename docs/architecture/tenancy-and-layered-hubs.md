# L3: tenancy and layered hubs

How hub instances are isolated and packaged, how usage is counted, how data is protected in transit and at rest, and where annotation layers fit. Source: XADR-SCITADEL-008 §1 (repo split and deploy topology), §8 (staged infrastructure: tenant simulation, stages 1 and 2, on-prem) and §17 (tiers).

> **Source legend.** As in [the tessera boundary](tessera-boundary.md). **A gap.** XADR-SCITADEL-008 has no text on "layered hubs" and none on annotation layers beyond "the client keeps annotations" (§12, §17); SYS-037 proposes four layers and defers their confirmation to L3. This file records what the sources decide and files the rest as S-004 and S-005. No commercial content here: billing and the hosted control plane belong to the private `nerdmachines/scitadel-cloud`. Every DES below is `proposed`.

| DES | Title | Realises | Uses |
|---|---|---|---|
| DES-047 | Tenant instance isolation and stage-portable packaging | SYS-035, SYS-038, SYS-039 | DES-001, DES-041 |
| DES-048 | Usage metering seam | SYS-036 | DES-032, DES-047 |
| DES-049 | Transport security, access control and secrets | SYS-041, SYS-040 | DES-047 |
| DES-050 | Annotation layers | SYS-037 | DES-032, DES-033, DES-047 |

## 1. Tenant isolation and packaging (DES-047)

- **One instance per tenant.** Each tenant runs its own hub instance in its own microVM with no shared writable mount and no shared credentials (SYS-035). Development and acceptance use the same packaging as the hosted tier: one microVM per simulated tenant on the stage-0 host, so isolation and metering paths run against the real artefact.
- **Stages change configuration only** (SYS-039): stage 0 on anvil; stage 1 a rented dedicated box for serving with object storage as the distribution point; stage 2 k3s plus microVMs for hosted org and personal spaces; on-prem. The backends are chosen at the composition root ([DES-001](tessera-boundary.md)); the data model, protocol and licence gating are identical across stages.
- **On-prem parity** (SYS-038). An on-prem hub runs the same binary and the same `.tsra` shards and speaks the same protocol ([DES-032](protocol.md)). The packaging (NixOS module, OCI image, Helm chart) lives in the **private** `nerdmachines/scitadel-hub-deploy`; the fleet consumes it pinned by tag and never patches it (D-002). Hub secrets are in their own sops file.
- **Repos.** The hub source is public (`AGPL-3.0-only OR LicenseRef-scitadel-Commercial`, [DES-056](licensing-and-tdm.md)); `scitadel-cloud` is a separate private repository (XADR-SCITADEL-008 §1).
- **Layered hubs** (S-005). Today a client has one configured hub with fall-through to live sources ([DES-053](client-app.md)); whether hubs chain is undecided, and no DES here assumes it.

## 2. Usage metering seam (DES-048)

The hub counts usage per tenant for the hosted tiers and **never meters the free local tier** (SYS-036; the local tier runs no hub). **Unresolved, pending S-008 ([#34](https://github.com/nerdmachines/scitadel-hub/issues/34)):** what is counted, in which units, how it reaches `scitadel-cloud` and how it reconciles (the 1 % bound of SYS-036) are not decided by XADR-SCITADEL-008, so no event shape is designed here.

## 3. Transport security, access control and secrets (DES-049)

- **In transit:** TLS 1.2 or newer on every hub endpoint; **at rest:** the hot pool is LUKS (SYS-041). No endpoint serves data anonymously.
- **S3 access** uses per-workload credentials with the roles of [L2 infrastructure](../vmodel/L2-infrastructure.md); the role table is owned by [#29](https://github.com/nerdmachines/scitadel-hub/issues/29) and is not restated here.
- **Secrets** (source keys, the pool's credentials) live in the sops file, are attached by the pool and never appear in a log, an error or a response (SYS-040, [DES-019](adapters-and-pool.md)).

## 4. Annotation layers (DES-050)

SYS-037 fixes four layers, **personal, group, organisation and global**, each annotation recording its layer and author; a read resolves most specific first; a write goes only to the layer the caller names; a lower layer never appears in a higher one except by an explicit **publish** that creates a new row in the higher layer. XADR-SCITADEL-008 §12 and §17 only say the client keeps annotations. **Unresolved, pending S-004 ([#30](https://github.com/nerdmachines/scitadel-hub/issues/30)):** where each layer is stored, whether the personal layer is client-side, the shape of a publish and the protocol call that carries annotations are not decided, so none is designed here. DES-050 is provisional: it states SYS-037 and nothing more.

## 5. Verification

| Test | Verifies | Method | Pass criterion |
|---|---|---|---|
| TEST-141 | DES-047 | Two tenant microVMs from the production packaging, each with a distinct fixture corpus and credentials, with cross-tenant read and write attempts and a stage-1 configuration swap | 0 cross-tenant reads; 0 shared writable mounts; 0 shared credentials; the swap changes no code and no format |
| TEST-142 | DES-048 | Fixture calls for two hosted tenants and the same calls through a local-tier hub | usage counted per tenant and not mixed across tenants; 0 meter events from the local tier (reconciliation waits for S-008) |
| TEST-143 | DES-049 | Port and endpoint scan of a fixture hub, anonymous and wrong-credential requests, a secrets canary in a request | 0 plaintext endpoints; 0 anonymous reads; the canary appears in no log, error or response; every S3 client has its own credential |
| TEST-144 | DES-050 | The permission matrix over the four layers: reads, writes and publishes by each of four fixture users | 0 leaks across the matrix; a read returns the most specific row first; layer and author present on 100 % of annotations (provisional until S-004) |
