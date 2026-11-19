# Paid read model probe

A sync, dependency-free Rust sketch of the paid read gate and [the paid read rule](../../tessera-boundary.md#the-paid-read-rule) (DES-057, DES-058; #28). It is a **sketch, not hub code**: it models what the rule decides on each path, with a `Vec<Row>` standing in for Arrow batches, std's `DefaultHasher` for blake3 and a row-count `statistics()` for DataFusion's. Nothing here is built by the hub or its CI.

```sh
./check.sh                      # builds, runs every case below, compares each exit code; exit 0 = all match
CARGO_TARGET_DIR=/elsewhere ./check.sh
```

Read with rustc and cargo 1.99.0: 306 checks, all match.

## Crates

| Crate | What |
|---|---|
| `boundary` | the opt-out log (hash-chained, head in `keep`), the five rules (`old`: round 6; `R1` to `R3`: review rounds 1 to 3; `R4`: section 1.2), `PaidTier` and its guards, the fixture, `tests/conformance.rs` (31 named cases) and two cases on `admitted(g)` itself in `src/lib.rs` |
| `caller` | `caller <old\|r1\|r2\|r3\|new> <case> [path]`: exit 0 = the case's bad row is served, 3 = not served, 4 = refused with an error; for `*_after_rebuild`, 0 = the re-admitted source is served, as intended |
| `cf_mint_scope`, `cf_held_stamp`, `cf_session_ctx` | compile-fail: E0624, E0308, E0616 (exit 101) |
| `compose`, `docforge` | the doctest reach rule R4: `docforge`'s doctest calls `compose` and builds only through workspace feature unification |
| `paid_serve`, `paid_serve_bad`, `datafusion`, `r5-fixtures/` | rule R5: a paid-serving crate depends on `boundary` only (`datafusion` is an empty stand-in), and `boundary` re-exports only the data-type allowlist (the fixtures' crate-root re-export and `pub type` aliases are rejected, including an absolute `::datafusion` path and a provider type inside generics) |

## Fixture

Cycle 1 allows sources A and B; items 10 (A's), 11 and 12 (B's) are `Clear` in cycle 1; item 13 has no verdict; item 14 has no verdict yet and is first seen in the delta (key 6); generation 1 is admitted. Key 4 has a base row (B, bulk) and a newer delta row (B, item 12). Two edges come from item 12, one to key 1 (A, item 10) and one to key 3. "Withdraw" records A `OptedOut` and completes cycle 2 without A, then records item 11 `Reserved`.

## Cases and expected exit codes

| Case | Before | After (`new`) |
|---|---|---|
| `held_stamp`, `held_scope`, `held_table`, `held_union`, `held_merged`, `register`, `catalog_source`, `refresh`, `merged_resurface`, `neighbours_endpoint`, `crop`, `aggregate` | `old` 0 | 3 |
| `lost_item` (a store hides the `Reserved`) | `old` 0 | 4 (`Integrity`) |
| `ddl` (`CREATE EXTERNAL TABLE` over the products) | `old` 0 | 4 (`Refused`) |
| `resolve`, `coverage`, `detach`, `capabilities` (window = 30), `neighbours_after_window` | — | 3 |
| `neighbours_in_window`: a batch inside `max_age` (the disclosed window) | — | 0 |

Per path: `search`, `resolve`, `neighbours`, `table`, `union`, `merged`, `session`, `coverage`, `crop` and `detach`.

| Case | Before | After (`new`) |
|---|---|---|
| `b1`: A `OptedOut`, cycle 2 still running | `r1` 0 on every path | 3 |
| `b2`: A allowed after generation 1's admission | `r1` 0 (`search` 3: the index was admitted) | 3; `b2_after_rebuild` 0 |
| `b1_rebuild`: A `OptedOut` in a running or aborted cycle, then a rebuild | `r2` 0 on every path | 3 |
| `refresh_src`: A `OptedOut` between the admission and a refresh | `r2` 0 on every path | 3 |
| `refresh_item`: item 11 `Reserved` between the admission and a refresh | `r2` 0 (`neighbours`, `coverage` 3: no row of item 11 there) | 3 |
| `reallow`: A withdrawn, then allowed again in a completed cycle, no rebuild | `r1` 0 on every path | 3; `reallow_after_rebuild` 0 |
| `x1`: A `OptedOut` in aborted cycle 2, `Allow` in running cycle 3, then a rebuild | `r3` 0 on every path | 3 |
| `first_seen`: item 14 `Clear` in completed cycle 1, then a refresh (SYS-021) | `r3` 3 (never added) | 0 (served; `neighbours`, `coverage` 3: no row of item 14 there); `first_seen_before` 3 |
| `readd`: item 14 `Reserved`, then `Clear`, then a refresh | — | 3; `readd_after_rebuild` 0 (as `first_seen`) |
| `refresh_source`: A allowed after the admission, then a refresh | — | 3 |
| `unchecked`: cycle 2 completes with no verdict for A, then a refresh | `r3` 0 on every path | 3 |
| `stale_parent`: a refresh naming g's older admission as its parent | `r3` 0 on every path | 4 (`Integrity`) |

The final review of #28 added five cases, each failing before its fix: `refresh_from_dangling_parent_is_integrity` (a parent seq not in the log was read as a build), `stray_allow_for_old_cycle_is_integrity` (a verdict naming a cycle other than the current one), `late_allow_after_refresh_does_not_readmit_dropped_source` (the unchecked-source rule read the whole log, not the log before `E2`), and, against the two surviving mutants, `refresh_skips_first_seen_item_with_unsettled_clear` (fails with `done.contains(c)` removed) and `refresh_never_adds_first_seen_item_of_dropped_source` (fails with `srcs.contains(src)` removed).

Not modelled: DataFusion's own planner (only the effect of `children()` and `statistics()` is), HTTP and MCP transport, and blake3.
