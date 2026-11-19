//! Named conformance cases of the paid-gate suite (tessera-boundary.md section 5) that this sketch can express.
use boundary::{ErrorKind, Provider, Row, World};
fn clean(r: &[Row]) -> bool { !World::served_withdrawn(r) }
fn a(r: &[Row]) -> bool { World::has(r, "A", None) }
fn read(w: &World, path: &str) -> Vec<Row> {
    match path {
        "search" => w.paid.search(1, "q").unwrap(), "resolve" => w.paid.resolve(1, &[1, 2, 3, 4, 5, 6]).unwrap(),
        "neighbours" => { let mut s = w.paid.neighbours(1).unwrap(); let mut v = vec![]; while let Some(b) = s.next_batch() { v.extend(b.unwrap()) } v }
        "table" => w.paid.table(1).unwrap().scan().unwrap(), "union" => w.paid.union(1).unwrap().scan().unwrap(),
        "merged" => w.paid.merged(1).unwrap().scan().unwrap(), "session" => w.paid.session(1).unwrap().sql_all().unwrap(),
        "crop" => [1, 2, 4, 6].iter().filter_map(|k| w.paid.crop(1, *k).ok()).collect(), "detach" => w.paid.detach(1, &[1, 2, 3, 4, 6]).unwrap(),
        _ => unreachable!(),
    }
}
const PATHS: [&str; 9] = ["search", "resolve", "neighbours", "table", "union", "merged", "session", "crop", "detach"];

#[test] fn held_paid_table_provider_after_cycle_flip_filters_row() { let w = World::new(); let p = w.paid.table(1).unwrap(); w.withdraw(); assert!(clean(&p.scan().unwrap())); }
#[test] fn held_paid_union_provider_after_withdrawal_filters_row() { let w = World::new(); let p = w.paid.union(1).unwrap(); w.withdraw(); assert!(clean(&p.scan().unwrap())); }
#[test] fn held_paid_merged_provider_after_withdrawal_filters_row() { let w = World::new(); let p = w.paid.merged(1).unwrap(); w.withdraw(); assert!(clean(&p.scan().unwrap())); }
#[test] fn registered_session_after_withdrawal_filters_row() { let w = World::new(); let s = w.paid.session(1).unwrap(); w.withdraw(); assert!(clean(&s.sql_all().unwrap())); }
#[test] fn aggregate_without_group_by_respects_withdrawal() { let w = World::new(); let s = w.paid.session(1).unwrap(); w.withdraw(); assert_eq!(s.count().unwrap(), 2); }
#[test] fn paid_session_refuses_create_external_table() { let w = World::new(); assert_eq!(w.paid.session(1).unwrap().sql("CREATE EXTERNAL TABLE t LOCATION 'x'").unwrap_err(), ErrorKind::Refused); }
#[test] fn paid_index_of_previous_cycle_filters_withdrawn_rows() { let w = World::new(); w.withdraw(); let r = w.paid.search(1, "q").unwrap(); assert!(clean(&r) && r.iter().any(|r| r.key == 3)); }
#[test] fn lost_item_reservation_is_integrity() { let w = World::new(); w.withdraw(); w.ledger.hide.set(Some(w.last_seq())); assert_eq!(w.paid.search(1, "q").unwrap_err(), ErrorKind::Integrity); }
#[test] fn item_without_clear_verdict_not_admitted() { let w = World::new(); assert!(!World::has(&w.paid.search(1, "q").unwrap(), "B", Some(13))); }
#[test] fn withdrawn_newest_row_does_not_resurface_older_version() { let w = World::new(); w.steps.item(12, true); assert!(!w.paid.merged(1).unwrap().scan().unwrap().iter().any(|r| r.key == 4)); }
#[test] fn withdrawn_row_not_served_via_resolve() { let w = World::new(); w.withdraw(); assert!(clean(&read(&w, "resolve"))); }
#[test] fn withdrawn_item_id_not_returned_by_vector_or_graph_leg() { let w = World::new(); w.withdraw(); assert!(!read(&w, "neighbours").iter().any(|r| r.key == 1)); }
#[test] fn withdrawn_crop_not_shown_to_reporting_user() { let w = World::new(); w.withdraw(); assert_eq!(w.paid.crop(1, 1).unwrap_err(), ErrorKind::NotFound); }
#[test] fn withdrawn_source_absent_from_coverage() { let w = World::new(); w.withdraw(); assert_eq!(w.paid.coverage(1).unwrap(), vec!["B"]); }
#[test] fn refresh_after_withdrawal_admits_under_current_set() { let w = World::new(); w.withdraw(); w.paid.refresh(1).unwrap(); assert!(clean(&w.paid.search(1, "q").unwrap())); }
#[test] fn generation_without_admission_refused() { let w = World::new(); assert_eq!(w.paid.search(2, "q").unwrap_err(), ErrorKind::Refused); }
#[test] fn in_flight_stream_applies_withdrawal_within_window() {
    let w = World::new(); let mut s = w.paid.neighbours(1).unwrap(); w.withdraw(); w.clock.0.set(31);
    while let Some(b) = s.next_batch() { assert!(clean(&b.unwrap())); }
}
#[test] fn optout_recorded_while_cycle_incomplete_is_filtered() {
    for p in PATHS { let w = World::new(); w.steps.opt_out(2, "A"); assert!(!a(&read(&w, p)), "{p}"); }
}
#[test] fn newly_allowed_source_appears_after_rebuild_only() {
    for p in PATHS {
        let w = World::new(); w.steps.allow(2, "B"); w.steps.complete(2); w.paid.rebuild(1).unwrap();
        w.steps.allow(3, "A"); w.steps.allow(3, "B"); w.steps.complete(3);
        assert!(!a(&read(&w, p)), "{p} before"); w.paid.rebuild(1).unwrap(); assert!(a(&read(&w, p)), "{p} after");
    }
}
#[test] fn optout_before_rebuild_in_incomplete_cycle_is_filtered() {
    for p in PATHS { let w = World::new(); w.steps.opt_out(2, "A"); w.paid.rebuild(1).unwrap(); assert!(!a(&read(&w, p)), "{p}"); }
}
#[test] fn withdrawal_between_admission_and_refresh_is_filtered() {
    for p in PATHS {
        let w = World::new(); w.steps.opt_out(2, "A"); w.paid.refresh(1).unwrap(); assert!(!a(&read(&w, p)), "{p} source");
        let w = World::new(); w.steps.item(11, true); w.paid.refresh(1).unwrap(); assert!(!World::has(&read(&w, p), "B", Some(11)), "{p} item");
    }
}
#[test] fn reallow_after_withdrawal_appears_after_rebuild_only() {
    for p in PATHS {
        let w = World::new(); w.steps.opt_out(2, "A"); w.steps.allow(2, "B"); w.steps.complete(2);
        w.steps.allow(3, "A"); w.steps.allow(3, "B"); w.steps.complete(3);
        assert!(!a(&read(&w, p)), "{p} before"); w.paid.refresh(1).unwrap(); assert!(!a(&read(&w, p)), "{p} after refresh");
        w.paid.rebuild(1).unwrap(); assert!(a(&read(&w, p)), "{p} after rebuild");
    }
}
#[test] fn reallow_in_incomplete_cycle_after_aborted_optout_not_admitted() {
    for p in PATHS { let w = World::new(); w.steps.opt_out(2, "A"); w.steps.allow(3, "A"); w.paid.rebuild(1).unwrap(); assert!(!a(&read(&w, p)), "{p}"); }
}
#[test] fn refresh_adds_first_seen_clear_item_of_admitted_source() {
    let w = World::new(); w.steps.item(14, false);
    assert!(!World::has(&read(&w, "table"), "B", Some(14)));
    w.paid.refresh(1).unwrap();
    for p in ["search", "table", "union", "merged", "session", "detach"] { assert!(World::has(&read(&w, p), "B", Some(14)), "{p}"); }
}
#[test] fn refresh_never_readds_previously_reserved_item() {
    let w = World::new(); w.steps.item(14, true); w.steps.item(14, false); w.paid.refresh(1).unwrap();
    for p in PATHS { assert!(!World::has(&read(&w, p), "B", Some(14)), "{p}"); }
    w.paid.rebuild(1).unwrap(); assert!(World::has(&read(&w, "table"), "B", Some(14)));
}
#[test] fn refresh_never_adds_source() {
    let w = World::new(); w.steps.allow(2, "B"); w.steps.complete(2); w.paid.rebuild(1).unwrap();
    w.steps.allow(3, "A"); w.steps.allow(3, "B"); w.steps.complete(3); w.paid.refresh(1).unwrap();
    for p in PATHS { assert!(!a(&read(&w, p)), "{p}"); }
}
#[test] fn refresh_drops_source_missing_from_completed_cycle() {
    let w = World::new(); w.steps.allow(2, "B"); w.steps.complete(2); w.paid.refresh(1).unwrap();
    for p in PATHS { assert!(!a(&read(&w, p)), "{p}"); }
}
#[test] fn refresh_from_stale_parent_is_integrity() {
    let w = World::new(); let first = w.admission_seq(1); w.paid.rebuild(1).unwrap(); let _ = w.paid.refresh_from(1, first);
    assert_eq!(w.paid.search(1, "q").unwrap_err(), ErrorKind::Integrity);
}
#[test] fn refresh_from_dangling_parent_is_integrity() {
    let w = World::new(); let _ = w.paid.refresh_from(1, Some(w.last_seq() + 100));
    assert_eq!(w.paid.search(1, "q").unwrap_err(), ErrorKind::Integrity);
}
#[test] fn stray_allow_for_old_cycle_is_integrity() {
    let w = World::new(); w.withdraw(); w.steps.allow(1, "A"); // cycle 1 completed before cycle 2 opened
    assert_eq!(w.paid.search(1, "q").unwrap_err(), ErrorKind::Integrity);
}
#[test] fn refresh_skips_first_seen_item_with_unsettled_clear() {
    let w = World::new(); w.steps.allow(2, "B"); w.steps.item(14, false); w.paid.refresh(1).unwrap(); // cycle 2 still running
    for p in PATHS { assert!(!World::has(&read(&w, p), "B", Some(14)), "{p}"); }
}
