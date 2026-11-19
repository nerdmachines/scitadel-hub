//! `caller <shape> <case> [path]`. Shapes: `old` (round 6), `r1`, `r2`, `r3` (review rounds 1 to 3), `new` (section 1.2).
//! Exit 0: the case's bad row is served (a withdrawn row, or a newly allowed source before its rebuild); for the
//! `*_after_rebuild` cases 0 means the source is served, as intended. 3: not served. 4: refused with an error.
use boundary::{old, ErrorKind, Policy, Provider, Row, World};
use std::process::exit;

fn report(r: Result<Vec<Row>, ErrorKind>, bad: &dyn Fn(&[Row]) -> bool) -> ! {
    match r {
        Ok(rows) => {
            let keys: Vec<String> = rows.iter().map(|r| format!("{}:{:?}", r.key, r.inputs)).collect();
            if bad(&rows) { println!("SERVED {keys:?}"); exit(0) }
            println!("NOT SERVED {keys:?}"); exit(3)
        }
        Err(k) => { println!("ERROR {k:?}"); exit(4) }
    }
}
fn withdrawn(r: &[Row]) -> bool { World::served_withdrawn(r) }
fn a_rows(r: &[Row]) -> bool { World::has(r, "A", None) }
fn item11(r: &[Row]) -> bool { World::has(r, "B", Some(11)) }
fn item14(r: &[Row]) -> bool { World::has(r, "B", Some(14)) }

/// Every paid read path that returns rows, for generation 1.
fn read(w: &World, path: &str) -> Result<Vec<Row>, ErrorKind> {
    let g = 1;
    match path {
        "search" => w.paid.search(g, "q"),
        "resolve" => w.paid.resolve(g, &[1, 2, 3, 4, 5, 6]),
        "neighbours" => { let mut s = w.paid.neighbours(g)?; let mut v = vec![]; while let Some(b) = s.next_batch() { v.extend(b?) } Ok(v) }
        "table" => w.paid.table(g)?.scan(),
        "union" => w.paid.union(g)?.scan(),
        "merged" => w.paid.merged(g)?.scan(),
        "session" => w.paid.session(g)?.sql("SELECT * FROM t"),
        "coverage" => Ok(w.paid.coverage(g)?.into_iter().map(|s| Row { key: 0, ver: 0, inputs: vec![(s, None)] }).collect()),
        "crop" => { let mut v = vec![]; for k in [1, 2, 4, 6] { match w.paid.crop(g, k) { Ok(r) => v.push(r), Err(ErrorKind::NotFound) => {}, Err(e) => return Err(e) } } Ok(v) }
        "detach" => w.paid.detach(g, &[1, 2, 3, 4, 6]),
        _ => { eprintln!("unknown path {path}"); exit(2) }
    }
}

fn main() {
    let a: Vec<String> = std::env::args().collect();
    let (shape, case) = (a[1].as_str(), a[2].as_str());
    let path = a.get(3).map(String::as_str).unwrap_or("");
    let policy = match shape { "r1" => Policy::R1, "r2" => Policy::R2, "r3" => Policy::R3, _ => Policy::R4 };
    let w = World::with(policy);
    let s = &w.steps;
    match (shape, case) {
        // ---- per-path cases, every shape but `old`
        (_, "b1") => { s.opt_out(2, "A"); report(read(&w, path), &a_rows) }                         // cycle 2 still running
        (_, "b2" | "b2_after_rebuild") => {
            s.allow(2, "B"); s.complete(2); w.paid.rebuild(1).unwrap();                               // g1 admitted without A
            s.allow(3, "A"); s.allow(3, "B"); s.complete(3);                                          // A newly allowed
            if case == "b2_after_rebuild" { w.paid.rebuild(1).unwrap(); }
            report(read(&w, path), &a_rows)
        }
        (_, "b1_rebuild") => { s.opt_out(2, "A"); w.paid.rebuild(1).unwrap(); report(read(&w, path), &a_rows) } // cycle 2 aborted or running
        (_, "refresh_src") => { s.opt_out(2, "A"); w.paid.refresh(1).unwrap(); report(read(&w, path), &a_rows) }
        (_, "refresh_item") => { s.item(11, true); w.paid.refresh(1).unwrap(); report(read(&w, path), &item11) }
        (_, "reallow" | "reallow_after_rebuild") => {
            s.opt_out(2, "A"); s.allow(2, "B"); s.complete(2);                                        // A withdrawn
            s.allow(3, "A"); s.allow(3, "B"); s.complete(3);                                          // A allowed again
            if case == "reallow_after_rebuild" { w.paid.rebuild(1).unwrap(); }
            report(read(&w, path), &a_rows)
        }
        // round 4: x1 is the reviewer's ordering; cycle 2 aborts, cycle 3 is still running at the rebuild
        (_, "x1") => { s.opt_out(2, "A"); s.allow(3, "A"); w.paid.rebuild(1).unwrap(); report(read(&w, path), &a_rows) }
        // item 14, first seen in the delta, Clear in completed cycle 1; exit 0 = served (intended after the refresh)
        (_, "first_seen" | "first_seen_before") => { s.item(14, false); if case == "first_seen" { w.paid.refresh(1).unwrap(); } report(read(&w, path), &item14) }
        (_, "readd" | "readd_after_rebuild") => {
            s.item(14, true); s.item(14, false); w.paid.refresh(1).unwrap();                              // ever Reserved
            if case == "readd_after_rebuild" { w.paid.rebuild(1).unwrap(); }
            report(read(&w, path), &item14)
        }
        (_, "refresh_source") => { s.allow(2, "B"); s.complete(2); w.paid.rebuild(1).unwrap(); s.allow(3, "A"); s.allow(3, "B"); s.complete(3); w.paid.refresh(1).unwrap(); report(read(&w, path), &a_rows) }
        (_, "unchecked") => { s.allow(2, "B"); s.complete(2); w.paid.refresh(1).unwrap(); report(read(&w, path), &a_rows) }   // cycle 2 has no verdict for A
        (_, "stale_parent") => { let first = w.admission_seq(1); w.paid.rebuild(1).unwrap(); w.paid.refresh_from(1, first).unwrap_or_else(|_| boundary::IndexStamp { g: 1 }); report(read(&w, path), &a_rows) }
        // ---- historical cases: the round-6 shape, then the gate
        ("old", "held_stamp") => { let i = old::ItemStore::default(); let st = old::build(&w, &old::paid(&w, &i)); w.withdraw(); report(old::search_stamp(&st), &withdrawn) }
        ("old", "held_scope") => { let i = old::ItemStore::default(); let sc = old::paid(&w, &i); let st = old::build(&w, &sc); w.withdraw(); w.clock.0.set(10); report(old::search_scope(&w, &sc, &st), &withdrawn) }
        ("old", "held_table" | "held_union" | "held_merged") => { let i = old::ItemStore::default(); let p = old::table(&w, &old::paid(&w, &i)); w.withdraw(); report(p.scan(), &withdrawn) }
        ("old", "register") => { let i = old::ItemStore::default(); let c = old::CallerSession { tables: vec![old::table(&w, &old::paid(&w, &i))] }; w.withdraw(); report(c.tables[0].scan(), &withdrawn) }
        ("old", "lost_item") => { let i = old::ItemStore::default(); i.reserved.borrow_mut().insert(11); i.reserved.borrow_mut().remove(&11); report(old::search_stamp(&old::build(&w, &old::paid(&w, &i))), &withdrawn) }
        ("old", "catalog_source") => { report(old::search_stamp(&old::build(&w, &old::catalog_scope(&["B"], &["A"]))), &withdrawn) }
        ("old", "refresh") => { let i = old::ItemStore::default(); let sc = old::paid(&w, &i); let mut st = old::build(&w, &sc); w.withdraw(); old::refresh(&w, &sc, &mut st); report(old::search_stamp(&st), &withdrawn) }
        ("old", "merged_resurface") => { s.item(12, true); let r = old::filter_then_merge(&w); exit(if r.iter().any(|r| r.key == 4) { 0 } else { 3 }) }
        ("old", "neighbours_endpoint") => { s.item(12, false); s.opt_out(2, "A"); s.allow(2, "B"); s.complete(2); report(Ok(old::neighbours_edge_only(&w)), &a_rows) }
        ("old", "crop") => { w.withdraw(); report(Ok([1, 2].iter().filter_map(|k| old::crop(&w, *k).ok()).collect()), &withdrawn) }
        ("old", "aggregate") => { let i = old::ItemStore::default(); let t = vec![old::table(&w, &old::paid(&w, &i))]; w.withdraw(); let n = boundary::count(&t).unwrap(); println!("count {n}"); exit(if n > 2 { 0 } else { 3 }) }
        ("old", "ddl") => { let c = old::CallerSession { tables: vec![old::external(&w)] }; w.withdraw(); report(c.tables[0].scan(), &withdrawn) }

        ("new", "held_stamp") => { let _st = w.paid.rebuild(1).unwrap(); w.withdraw(); report(w.paid.search(1, "q"), &withdrawn) }
        ("new", "held_scope") => { w.withdraw(); w.clock.0.set(10); report(w.paid.search(1, "q"), &withdrawn) }
        ("new", "held_table") => { let p = w.paid.table(1).unwrap(); w.withdraw(); report(p.scan(), &withdrawn) }
        ("new", "held_union") => { let p = w.paid.union(1).unwrap(); w.withdraw(); report(p.scan(), &withdrawn) }
        ("new", "held_merged") => { let p = w.paid.merged(1).unwrap(); w.withdraw(); report(p.scan(), &withdrawn) }
        ("new", "register") => { let c = w.paid.session(1).unwrap(); w.withdraw(); report(c.sql_all(), &withdrawn) }
        ("new", "lost_item") => { w.withdraw(); w.ledger.hide.set(Some(w.last_seq())); report(w.paid.search(1, "q"), &withdrawn) }
        ("new", "catalog_source") => { w.withdraw(); w.paid.rebuild(1).unwrap(); report(w.paid.search(1, "q"), &withdrawn) }
        ("new", "refresh") => { w.withdraw(); w.paid.refresh(1).unwrap(); report(w.paid.search(1, "q"), &withdrawn) }
        ("new", "merged_resurface") => { s.item(12, true); let r = w.paid.merged(1).unwrap().scan().unwrap(); exit(if r.iter().any(|r| r.key == 4) { 0 } else { 3 }) }
        ("new", "neighbours_endpoint") => { s.opt_out(2, "A"); s.allow(2, "B"); s.complete(2); report(read(&w, "neighbours"), &a_rows) }
        ("new", "crop") => { w.withdraw(); report(read(&w, "crop"), &withdrawn) }
        ("new", "aggregate") => { let c = w.paid.session(1).unwrap(); w.withdraw(); let n = c.count().unwrap(); println!("count {n}"); exit(if n > 2 { 0 } else { 3 }) }
        ("new", "ddl") => { let c = w.paid.session(1).unwrap(); w.withdraw(); report(c.sql("CREATE EXTERNAL TABLE t STORED AS PARQUET LOCATION 'products/'"), &withdrawn) }
        // ---- the gate only
        ("new", "resolve") => { w.withdraw(); report(read(&w, "resolve"), &withdrawn) }
        ("new", "coverage") => { w.withdraw(); report(read(&w, "coverage"), &a_rows) }
        ("new", "detach") => { w.withdraw(); report(read(&w, "detach"), &withdrawn) }
        ("new", "capabilities") => { let win = w.paid.capabilities(1).unwrap(); println!("opt_out_window {win}"); exit(if win == 30 { 3 } else { 0 }) }
        ("new", "neighbours_in_window") => { let mut st = w.paid.neighbours(1).unwrap(); w.withdraw(); w.clock.0.set(20); report(st.next_batch().unwrap(), &a_rows) }
        ("new", "neighbours_after_window") => { let mut st = w.paid.neighbours(1).unwrap(); w.withdraw(); w.clock.0.set(31); let mut v = vec![]; while let Some(b) = st.next_batch() { v.extend(b.unwrap()) } report(Ok(v), &a_rows) }
        _ => { eprintln!("unknown case {shape} {case}"); exit(2) }
    }
}
