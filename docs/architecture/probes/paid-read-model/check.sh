#!/usr/bin/env bash
# Runs every case of the paid read model probe and compares each exit code with the documented one (README.md).
# Exit 0 when all match. Uses $CARGO_TARGET_DIR if set (default: ./target, ignored by git).
set -u
cd "$(dirname "$0")"
export CARGO_TARGET_DIR="${CARGO_TARGET_DIR:-$PWD/target}"
fail=0
expect() { # expect <code> <description> <command...>
  local want=$1 what=$2; shift 2
  "$@" >/dev/null 2>&1; local got=$?
  if [ "$got" = "$want" ]; then printf 'ok   %-58s %s\n' "$what" "$got"; else printf 'FAIL %-58s got %s want %s\n' "$what" "$got" "$want"; fail=1; fi
}
cargo build -q -p caller || exit 2
B="$CARGO_TARGET_DIR/debug/caller"
# Historical and per-path-family cases: before (old or an earlier round) -> after (section 1.2).
for c in held_stamp held_scope held_table held_union held_merged register catalog_source refresh merged_resurface \
         neighbours_endpoint crop aggregate; do
  expect 0 "old $c" "$B" old "$c"; expect 3 "new $c" "$B" new "$c"
done
expect 0 "old lost_item" "$B" old lost_item; expect 4 "new lost_item (Integrity)" "$B" new lost_item
expect 0 "old ddl" "$B" old ddl;             expect 4 "new ddl (Refused)" "$B" new ddl
for c in resolve coverage detach capabilities neighbours_after_window; do expect 3 "new $c" "$B" new "$c"; done
expect 0 "new neighbours_in_window (the disclosed window)" "$B" new neighbours_in_window
# Per-path cases over every path with rows.
PATHS="search resolve neighbours table union merged session coverage crop detach"
for p in $PATHS; do
  expect 0 "r1  b1 $p" "$B" r1 b1 "$p";                       expect 3 "new b1 $p" "$B" new b1 "$p"
  if [ "$p" = search ]; then expect 3 "r1  b2 $p (index admitted)" "$B" r1 b2 "$p"; else expect 0 "r1  b2 $p" "$B" r1 b2 "$p"; fi
  expect 3 "new b2 $p" "$B" new b2 "$p";                      expect 0 "new b2_after_rebuild $p" "$B" new b2_after_rebuild "$p"
  expect 0 "r2  b1_rebuild $p" "$B" r2 b1_rebuild "$p";       expect 3 "new b1_rebuild $p" "$B" new b1_rebuild "$p"
  expect 0 "r2  refresh_src $p" "$B" r2 refresh_src "$p";     expect 3 "new refresh_src $p" "$B" new refresh_src "$p"
  case $p in neighbours|coverage) want=3 ;; *) want=0 ;; esac # item 11 has no edge and coverage lists sources
  expect $want "r2  refresh_item $p" "$B" r2 refresh_item "$p"; expect 3 "new refresh_item $p" "$B" new refresh_item "$p"
  expect 0 "r1  reallow $p" "$B" r1 reallow "$p";             expect 3 "new reallow $p" "$B" new reallow "$p"
  expect 0 "new reallow_after_rebuild $p" "$B" new reallow_after_rebuild "$p"
  # round 4. Item 14 has rows on every path but neighbours and coverage, where "served" cannot occur (3).
  case $p in neighbours|coverage) i=3 ;; *) i=0 ;; esac
  expect 0 "r3  x1 $p" "$B" r3 x1 "$p";                       expect 3 "new x1 $p" "$B" new x1 "$p"
  expect 3 "r3  first_seen $p (SYS-021 missed)" "$B" r3 first_seen "$p"; expect $i "new first_seen $p" "$B" new first_seen "$p"
  expect 3 "new first_seen_before $p" "$B" new first_seen_before "$p"
  expect 3 "new readd $p" "$B" new readd "$p";               expect $i "new readd_after_rebuild $p" "$B" new readd_after_rebuild "$p"
  expect 3 "new refresh_source $p" "$B" new refresh_source "$p"
  expect 0 "r3  unchecked $p" "$B" r3 unchecked "$p";         expect 3 "new unchecked $p" "$B" new unchecked "$p"
  expect 0 "r3  stale_parent $p" "$B" r3 stale_parent "$p"
  expect 4 "new stale_parent $p (Integrity)" "$B" new stale_parent "$p"
done
# Named conformance cases, compile-fail cases, the doctest reach rule (R4) and the paid-serving dependency rule (R5).
expect 0 "libtest conformance cases" cargo test -q -p boundary
for c in cf_mint_scope cf_held_stamp cf_session_ctx; do expect 101 "compile-fail $c" cargo check -q -p "$c"; done
expect 0 "docforge: cargo test --workspace --doc (unified features)" cargo test -q --workspace --doc
expect 0 "docforge: round-6 R4, cargo check --all-targets" cargo check -q -p docforge --all-targets
expect 101 "docforge: R4, cargo test -p docforge --doc" cargo test -q -p docforge --doc
r5() { [ "$(cargo tree -q -p "$1" -e normal --prefix none --depth 1 | tail -n +2 | awk '{print $1}' | sort -u | tr '\n' ' ')" = "boundary " ]; }
expect 0 "R5 paid_serve depends on boundary only" r5 paid_serve
expect 1 "R5 paid_serve_bad (datafusion) rejected" r5 paid_serve_bad
# R5, second half: hub-boundary re-exports only the data-type allowlist, never a crate root or a provider type.
# A `pub type` alias naming any path is a re-export too, wherever the path sits: right after `=`, absolute
# (`= ::datafusion::...`) or inside generics (`= Arc<dyn datafusion::...>`). A local alias names no path.
reexports() { ! grep -hE '^\s*pub\s+(use|extern\s+crate|type\s+\w+(<[^>]*>)?\s*=.*::)' "$@" \
  | grep -vE 'pub (use|type \w+ =) (::)?[a-z_:]*::(RecordBatch|SchemaRef|ArrayRef|SendableRecordBatchStream);' | grep -q .; }
expect 0 "R5 boundary re-exports only the allowlist" reexports boundary/src/*.rs
expect 1 "R5 a datafusion crate-root re-export rejected" reexports r5-fixtures/reexport_bad.rs
expect 1 "R5 a pub type alias of a provider type rejected" reexports r5-fixtures/type_alias_bad.rs
expect 1 "R5 a pub type alias through ::datafusion rejected" reexports r5-fixtures/type_alias_leading_colons_bad.rs
expect 1 "R5 a provider type inside a pub type's generics rejected" reexports r5-fixtures/type_alias_generic_bad.rs
[ $fail = 0 ] && echo "all cases match" || echo "MISMATCH"
exit $fail
