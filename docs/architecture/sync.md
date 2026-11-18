# L3: sync

How the OpenAlex lab mirror stays fresh on the free key. Source: XADR-SCITADEL-008 §5 (OpenAlex sync strategy). The HTTP work (pacing, credits, retries, resumable downloads) is the shared pool of [adapters and pool](adapters-and-pool.md) ([DES-019](adapters-and-pool.md)); the sync scheduler below decides what to ask it for. The patent counterpart is [patents](patents.md).

> **Source legend.** As in [the tessera boundary](tessera-boundary.md). Dollar budgets of the ADR are not copied: the allowance is a configuration value read from the source's published terms (see [DES-019](adapters-and-pool.md)). The page size is C-003 (SYS-003 says 200, the ADR's own source cites 100). Every DES below is `proposed`.

| DES | Title | Realises | Uses |
|---|---|---|---|
| DES-028 | OpenAlex sync scheduler: base subset, subscriptions, rolling refresh, on demand | SYS-003, SYS-043 | DES-018, DES-019, DES-014 |
| DES-029 | Merge and deletion reconciliation | SYS-005, SYS-003 | DES-005, DES-024, DES-028 |

## 1. Sync scheduler (DES-028)

| Job | What | Budget and rule |
|---|---|---|
| Base | The quarterly public snapshot filtered to a subset (topic, field, subfield, institution, source or the citation neighbourhood of the lab's libraries), read from the public bucket through DataFusion over S3 without downloading the full dump | 5 to 50 GB per subset *(estimate)*; the subset filter is recorded in the product ([DES-023](data-model-and-lifecycle.md)) |
| 1. Subscriptions | Per subscribed topic, author, institution or source, a list query with `from_publication_date = last_run − lookback` (default 90 days), cursor paging | one request ledger entry per page, debited before it is sent (DES-019) |
| 2. Rolling refresh | Re-fetch known works 100 IDs per call, hottest first: works in members' libraries, recently read, recently cited | takes the rest of the day's allowance; a 5M-work subset turns over in about five days *(estimate)* |
| 3. On demand | A single-entity GET when a client opens a paper | free of list credits; goes through the pool like the others |
| 4. Merges and deletions | Section 2 (DES-029) | |

- **Credits.** The pool reads `X-RateLimit-Credits-Used` from every response and the scheduler stops before the day's allowance is spent; it is never a heuristic of the scheduler (SYS-003). The key never appears in a log or an error (SYS-040).
- **Run record.** Every sync cycle is an ordinary run with pinned inputs and a ledger entry ([DES-014](tessera-boundary.md)); a resume never spends twice (SYS-061).
- **Telemetry.** Freshness per subscription, credits used and queue depth go to the observability seam (SYS-043).
- **Accepted gaps (documented, not bugs).** A work indexed late with a publication date older than the lookback waits for the next quarterly snapshot; changes to works outside the subset are not tracked.
- **Optional paid path.** With an institutional membership the scheduler's source of deltas changes to `from_updated_date` sync; the storage model and every DES here are unchanged. It is a second `IngestAdapter` descriptor ([DES-018](adapters-and-pool.md)), off by default (open question 4 of the ADR).
- **Why not a live mirror of everything.** The change feed is what the upstream sells; reconstructing it from the free key would mean re-fetching everything, and a full mirror would exceed the stage-0 disk. Not a goal.
- **Embeddings.** Existing CC0 embedding sets are taken first and the hub computes embeddings only for works they miss, as a GPU job ([DES-022](adapters-and-pool.md), SYS-050). Their model and dimension become a service definition ([DES-015](tessera-boundary.md)); their schemas are not yet verified (XADR-SCITADEL-008 §5).

## 2. Merge and deletion reconciliation (DES-029)

- A refresh that returns a different ID marks a **merge**; one that returns nothing marks a **deletion**. Each becomes a tombstone row `(id, merged → W… | deleted)` in the next delta ([DES-005](tessera-boundary.md)).
- Each quarterly snapshot reconciles against its `merged_ids` and `deleted_ids` files before it becomes the new base; a disagreement between the two evidences is recorded, with both, in the run and never silently resolved.
- A tombstone redirects or drops its key on read ([DES-025](query-engine.md)); the retraction flags of [DES-026](retrieval.md) are independent of it.

## 3. Verification

| Test | Verifies | Method | Pass criterion |
|---|---|---|---|
| TEST-122 | DES-028 | A recorded OpenAlex fixture server with a credit header counting down, run for three cycles with a kill during paging | 0 requests beyond the allowance; a resumed cycle spends nothing twice; the late-indexed work is absent until the snapshot; the key appears in no log |
| TEST-123 | DES-029 | A fixture refresh set with a merged ID, a vanished ID and a quarterly snapshot whose `merged_ids` disagrees with the refresh | tombstones written for both; reads redirect and drop; the disagreement recorded with both sources; the next base contains neither tombstoned key |
