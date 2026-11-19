//! Paid read model probe (#28): a sync, dependency-free sketch of tessera-boundary.md section 1.2.
//! `Policy::R3` is the normative rule of section 1.2; R1 and R2 are the rules of review rounds 1 and 2, and `old` is
//! the round-6 shape, kept so that every historical case can be run before and after.
//! Stand-ins: std's DefaultHasher for blake3, Vec<Row> for Arrow batches, a row-count `statistics()` for DataFusion's.
use std::cell::{Cell, RefCell};
use std::collections::hash_map::DefaultHasher;
use std::collections::{HashMap, HashSet, VecDeque};
use std::hash::{Hash, Hasher};
use std::rc::Rc;

pub type Src = &'static str;
/// One input of a row: its source and, for an item-level fetch, its item. A derived row lists every input (C5).
pub type In = (Src, Option<u32>);
#[derive(Clone, Debug, PartialEq)]
pub struct Row { pub key: u32, pub ver: u32, pub inputs: Vec<In> }
fn row(key: u32, ver: u32, inputs: &[In]) -> Row { Row { key, ver, inputs: inputs.to_vec() } }
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ErrorKind { StaleStamp, Integrity, Refused, NotFound }
pub type HubResult<T> = Result<T, ErrorKind>;

// ------------------------------------------------------------------ the recorded opt-out log and its head in `keep`
#[derive(Clone, Debug, Hash)]
pub enum Ev { Allow { cycle: u32, src: Src }, OptedOut { cycle: u32, src: Src }, Cycle { cycle: u32 },
              Item { item: u32, reserved: bool }, Admission { g: u32, parent: Option<u64> } }
#[derive(Clone, Debug)]
pub struct Recorded { body: Ev, seq: u64, prev: u64, digest: u64 }
fn digest(b: &Ev, seq: u64, prev: u64) -> u64 { let mut h = DefaultHasher::new(); (b, seq, prev).hash(&mut h); h.finish() }
/// In-memory ledger; `hide` makes it a faulty store that loses one record.
#[derive(Default)]
pub struct MemLedger { log: RefCell<Vec<Recorded>>, pub hide: Cell<Option<u64>> }
impl MemLedger { fn log(&self) -> Vec<Recorded> { self.log.borrow().iter().filter(|r| Some(r.seq) != self.hide.get()).cloned().collect() } }
#[derive(Default)]
pub struct Clock(pub Cell<u64>);

/// The `Steps` authority: the only writer; every append also moves the head kept in `keep`.
#[derive(Clone)]
pub struct Steps { ledger: Rc<MemLedger>, head: Rc<Cell<(u64, u64)>> }
impl Steps {
    fn append(&self, body: Ev) -> u64 {
        let (seq, prev) = self.ledger.log.borrow().last().map(|r| (r.seq + 1, r.digest)).unwrap_or((1, 0));
        let d = digest(&body, seq, prev);
        self.ledger.log.borrow_mut().push(Recorded { body, seq, prev, digest: d });
        self.head.set((seq, d));
        seq
    }
    pub fn allow(&self, cycle: u32, src: Src) { self.append(Ev::Allow { cycle, src }); }
    pub fn opt_out(&self, cycle: u32, src: Src) { self.append(Ev::OptedOut { cycle, src }); }
    pub fn complete(&self, cycle: u32) { self.append(Ev::Cycle { cycle }); }
    pub fn item(&self, item: u32, reserved: bool) { self.append(Ev::Item { item, reserved }); }
}
fn checked_log(l: &MemLedger, head: (u64, u64)) -> HubResult<Vec<Recorded>> {
    let log = l.log();
    let (mut prev, mut seq) = (0, 1);
    for r in &log {
        if r.seq != seq || r.prev != prev || r.digest != digest(&r.body, r.seq, r.prev) { return Err(ErrorKind::Integrity); }
        prev = r.digest; seq += 1;
    }
    if head.0 > 0 && ((log.len() as u64) < head.0 || log[(head.0 - 1) as usize].digest != head.1) { return Err(ErrorKind::Integrity); }
    Ok(log)
}

// ------------------------------------------------------------------ the read predicate of each rule
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Policy { R1, R2, R3 }
/// served(x) = x in (srcs, items) and not in (w_src, w_items); a row is served when every input is.
#[derive(Clone, Debug, Default)]
pub struct Pred { srcs: HashSet<Src>, items: HashSet<u32>, w_src: HashSet<Src>, w_items: HashSet<u32> }
impl Pred {
    fn input(&self, (s, i): &In) -> bool {
        self.srcs.contains(s) && !self.w_src.contains(s) && i.map_or(true, |i| self.items.contains(&i) && !self.w_items.contains(&i))
    }
    pub fn admits(&self, r: &Row) -> bool { r.inputs.iter().all(|x| self.input(x)) }
}
fn newest_cycle(log: &[Recorded]) -> Option<u32> { log.iter().filter_map(|r| match r.body { Ev::Cycle { cycle } => Some(cycle), _ => None }).last() }
fn allows(log: &[Recorded], cycle: Option<u32>) -> HashSet<Src> {
    log.iter().filter_map(|r| match r.body { Ev::Allow { cycle: c, src } if Some(c) == cycle => Some(src), _ => None }).collect()
}
/// Newest verdict per source (true = OptedOut) and per item (true = Reserved), whatever the cycle state.
fn newest(log: &[Recorded]) -> (HashMap<Src, bool>, HashMap<u32, bool>) {
    let (mut s, mut i) = (HashMap::new(), HashMap::new());
    for r in log { match r.body { Ev::Allow { src, .. } => { s.insert(src, false); } Ev::OptedOut { src, .. } => { s.insert(src, true); }
                                  Ev::Item { item, reserved } => { i.insert(item, reserved); } _ => {} } }
    (s, i)
}
fn admission_pos(log: &[Recorded], g: u32) -> HubResult<usize> {
    log.iter().rposition(|r| matches!(r.body, Ev::Admission { g: x, .. } if x == g)).ok_or(ErrorKind::Refused)
}
fn parent(log: &[Recorded], pos: usize) -> Option<usize> {
    match log[pos].body { Ev::Admission { parent: Some(p), .. } => log.iter().position(|r| r.seq == p), _ => None }
}
/// Section 1.2: admitted(g) at the admission at `pos`. A build admits x when its newest verdict before E is an allow and
/// the newest completed cycle allowed it (items: newest verdict Clear). A refresh is its parent minus every x with a
/// withdrawal recorded between the two admissions; it never adds.
fn admitted_r3(log: &[Recorded], pos: usize) -> (HashSet<Src>, HashSet<u32>) {
    match parent(log, pos) {
        None => {
            let pre = &log[..pos];
            let (ns, ni) = newest(pre);
            let srcs = allows(pre, newest_cycle(pre)).into_iter().filter(|s| ns.get(s) == Some(&false)).collect();
            let items = ni.into_iter().filter(|(_, r)| !r).map(|(i, _)| i).collect();
            (srcs, items)
        }
        Some(pp) => {
            let (mut srcs, mut items) = admitted_r3(log, pp);
            for r in &log[pp + 1..pos] { match r.body { Ev::OptedOut { src, .. } => { srcs.remove(src); }
                                                        Ev::Item { item, reserved: true } => { items.remove(&item); } _ => {} } }
            (srcs, items)
        }
    }
}
fn derive(policy: Policy, log: &[Recorded], g: u32) -> HubResult<Pred> {
    let (ns, ni) = newest(log);
    match policy {
        // Round 1: the newest completed cycle's allow-list and the newest item verdicts, for every read.
        Policy::R1 => Ok(Pred { srcs: allows(log, newest_cycle(log)), items: ni.into_iter().filter(|(_, r)| !r).map(|(i, _)| i).collect(), ..Default::default() }),
        // Round 2 as written at tb:83 and ap:66: sources of the newest completed cycle before the root admission (a refresh
        // keeps its parent's sources), withdrawals counted only after the newest admission.
        Policy::R2 => {
            let pos = admission_pos(log, g)?;
            let mut root = pos; while let Some(p) = parent(log, root) { root = p; }
            let srcs = allows(&log[..root], newest_cycle(&log[..root]));
            // the parent's items, plus the delta's own (first seen after the root admission) with a Clear before this one
            let root_items = newest(&log[..root]).1;
            let items = newest(&log[..pos]).1.into_iter()
                .filter(|(i, r)| match root_items.get(i) { Some(rr) => !rr, None => !r }).map(|(i, _)| i).collect();
            let (mut w_src, mut w_items) = (HashSet::new(), HashSet::new());
            for r in &log[pos + 1..] { match r.body { Ev::OptedOut { src, .. } => { w_src.insert(src); }
                                                      Ev::Item { item, reserved: true } => { w_items.insert(item); } _ => {} } }
            Ok(Pred { srcs, items, w_src, w_items })
        }
        // Section 1.2: admitted(g) and not withdrawn(now), and not withdrawn since g's admission.
        Policy::R3 => {
            let pos = admission_pos(log, g)?;
            let (srcs, items) = admitted_r3(log, pos);
            let mut w_src: HashSet<Src> = ns.into_iter().filter(|(_, o)| *o).map(|(s, _)| s).collect();
            let mut w_items: HashSet<u32> = ni.into_iter().filter(|(_, r)| *r).map(|(i, _)| i).collect();
            for r in &log[pos + 1..] { match r.body { Ev::OptedOut { src, .. } => { w_src.insert(src); }
                                                      Ev::Item { item, reserved: true } => { w_items.insert(item); } _ => {} } }
            Ok(Pred { srcs, items, w_src, w_items })
        }
    }
}

/// Re-derived per scan; reused per batch only while younger than `max_age` (the disclosed window).
pub struct ExclusionView { ledger: Rc<MemLedger>, head: Rc<Cell<(u64, u64)>>, clock: Rc<Clock>, pub max_age: u64, policy: Policy, snap: RefCell<Option<(Pred, u64)>> }
impl ExclusionView {
    fn for_scan(&self, g: u32) -> HubResult<Pred> {
        let p = derive(self.policy, &checked_log(&self.ledger, self.head.get())?, g)?;
        *self.snap.borrow_mut() = Some((p.clone(), self.clock.0.get()));
        Ok(p)
    }
    fn for_batch(&self, g: u32) -> HubResult<Pred> {
        if let Some((p, at)) = &*self.snap.borrow() { if self.clock.0.get() - at <= self.max_age { return Ok(p.clone()); } }
        self.for_scan(g)
    }
}

// ------------------------------------------------------------------ products, index and the gate
pub struct Data { pub base: Vec<Row>, pub delta: Vec<Row>, pub edges: Vec<Row>, index: RefCell<Vec<Row>> }
/// Newest-wins over base and delta (DES-005), before any exclusion.
fn merged(d: &Data) -> Vec<Row> {
    let mut m: HashMap<u32, Row> = HashMap::new();
    for r in d.base.iter().chain(d.delta.iter()) { let e = m.entry(r.key).or_insert(r.clone()); if r.ver >= e.ver { *e = r.clone(); } }
    let mut v: Vec<Row> = m.into_values().collect(); v.sort_by_key(|r| r.key); v
}
pub struct Scoped { g: u32, set: Pred }
impl Scoped { pub(crate) fn mint(v: &ExclusionView, g: u32) -> HubResult<Scoped> { Ok(Scoped { g, set: v.for_scan(g)? }) } }
pub struct IndexStamp { pub g: u32 }
pub trait Provider { fn scan(&self) -> HubResult<Vec<Row>>; fn statistics(&self) -> Option<usize>; }
/// A leaf: owns its rows, exposes no children and no statistics (C2).
pub struct GuardedProvider { view: Rc<ExclusionView>, data: Rc<Data>, g: u32 }
impl Provider for GuardedProvider {
    fn scan(&self) -> HubResult<Vec<Row>> { let s = self.view.for_scan(self.g)?; Ok(merged(&self.data).into_iter().filter(|r| s.admits(r)).collect()) }
    fn statistics(&self) -> Option<usize> { None }
}
pub struct GuardedStream { view: Rc<ExclusionView>, batches: VecDeque<Vec<Row>>, g: u32 }
impl GuardedStream {
    pub fn next_batch(&mut self) -> Option<HubResult<Vec<Row>>> {
        let b = self.batches.pop_front()?;
        Some(self.view.for_batch(self.g).map(|s| b.into_iter().filter(|r| s.admits(r)).collect()))
    }
}
/// `count(*)` as DataFusion's aggregate-statistics rule answers it: from statistics when a provider reports them.
pub fn count(tables: &[Box<dyn Provider>]) -> HubResult<usize> {
    let mut n = 0; for t in tables { n += match t.statistics() { Some(c) => c, None => t.scan()?.len() }; } Ok(n)
}
struct SessionCtx { tables: Vec<Box<dyn Provider>> }
pub struct PaidSession { ctx: SessionCtx }
impl PaidSession {
    pub fn sql_all(&self) -> HubResult<Vec<Row>> { let mut o = vec![]; for t in &self.ctx.tables { o.extend(t.scan()?); } Ok(o) }
    pub fn count(&self) -> HubResult<usize> { count(&self.ctx.tables) }
    /// DDL, DML and statements disabled (C3).
    pub fn sql(&self, stmt: &str) -> HubResult<Vec<Row>> {
        let s = stmt.trim_start().to_ascii_uppercase();
        if ["CREATE", "COPY", "INSERT", "DROP", "SET"].iter().any(|k| s.starts_with(k)) { return Err(ErrorKind::Refused); }
        self.sql_all()
    }
}
pub struct PaidTier { view: Rc<ExclusionView>, data: Rc<Data>, steps: Steps }
impl PaidTier {
    fn admission_seq(&self, g: u32) -> Option<u64> {
        self.steps.ledger.log().iter().rev().find(|r| matches!(r.body, Ev::Admission { g: x, .. } if x == g)).map(|r| r.seq)
    }
    /// The full rebuild: commits g's admission (the purge point), then builds the index under it.
    pub fn rebuild(&self, g: u32) -> HubResult<IndexStamp> {
        self.steps.append(Ev::Admission { g, parent: None });
        let sc = Scoped::mint(&self.view, g)?;
        *self.data.index.borrow_mut() = merged(&self.data).into_iter().filter(|r| sc.set.admits(r)).collect();
        Ok(IndexStamp { g: sc.g })
    }
    /// A refresh: commits an admission whose parent is g's previous one, then adds the delta segment under it.
    pub fn refresh(&self, g: u32) -> HubResult<IndexStamp> {
        let parent = self.admission_seq(g);
        self.steps.append(Ev::Admission { g, parent });
        let sc = Scoped::mint(&self.view, g)?;
        let mut idx = self.data.index.borrow_mut();
        idx.retain(|r| !self.data.delta.iter().any(|d| d.key == r.key));
        idx.extend(self.data.delta.iter().filter(|r| sc.set.admits(r)).cloned());
        Ok(IndexStamp { g: sc.g })
    }
    pub fn search(&self, g: u32, _q: &str) -> HubResult<Vec<Row>> {
        let sc = Scoped::mint(&self.view, g)?; Ok(self.data.index.borrow().iter().filter(|r| sc.set.admits(r)).cloned().collect())
    }
    pub fn resolve(&self, g: u32, keys: &[u32]) -> HubResult<Vec<Row>> {
        let sc = Scoped::mint(&self.view, g)?; Ok(merged(&self.data).into_iter().filter(|r| keys.contains(&r.key) && sc.set.admits(r)).collect())
    }
    pub fn neighbours(&self, g: u32) -> HubResult<GuardedStream> {
        Scoped::mint(&self.view, g)?; Ok(GuardedStream { view: self.view.clone(), batches: self.data.edges.iter().map(|r| vec![r.clone()]).collect(), g })
    }
    pub fn capabilities(&self, g: u32) -> HubResult<u64> { Scoped::mint(&self.view, g)?; Ok(self.view.max_age) }
    /// Sources with a served row (protocol `coverage`).
    pub fn coverage(&self, g: u32) -> HubResult<Vec<Src>> {
        let mut v: Vec<Src> = self.table(g)?.scan()?.iter().map(|r| r.inputs[0].0).collect(); v.sort(); v.dedup(); Ok(v)
    }
    /// A region crop (DES-039): the element is resolved through the gate first; the render is its row here.
    pub fn crop(&self, g: u32, key: u32) -> HubResult<Row> { self.resolve(g, &[key])?.pop().ok_or(ErrorKind::NotFound) }
    /// `detach` of tracked works: built from `resolve` and `table` only.
    pub fn detach(&self, g: u32, keys: &[u32]) -> HubResult<Vec<Row>> {
        let mut v = self.resolve(g, keys)?; v.extend(self.table(g)?.scan()?.into_iter().filter(|r| keys.contains(&r.key))); Ok(v)
    }
    pub fn table(&self, g: u32) -> HubResult<GuardedProvider> { Scoped::mint(&self.view, g)?; Ok(GuardedProvider { view: self.view.clone(), data: self.data.clone(), g }) }
    pub fn union(&self, g: u32) -> HubResult<GuardedProvider> { self.table(g) }
    pub fn merged(&self, g: u32) -> HubResult<GuardedProvider> { self.table(g) }
    pub fn session(&self, g: u32) -> HubResult<PaidSession> { Ok(PaidSession { ctx: SessionCtx { tables: vec![Box::new(self.merged(g)?)] } }) }
}

// ------------------------------------------------------------------ the fixture
pub struct World { pub steps: Steps, pub paid: PaidTier, pub ledger: Rc<MemLedger>, pub clock: Rc<Clock>, view: Rc<ExclusionView>, pub data: Rc<Data> }
impl World {
    pub fn new() -> World { World::with(Policy::R3) }
    /// Cycle 1 allows A and B; items 10, 11, 12 Clear; item 13 has no verdict; g1 admitted.
    /// Key 4: base row B/bulk v1, delta row B/item 12 v2. Edges: B/item 12 cites key 1 (A/item 10) and key 3 (B/bulk).
    pub fn with(policy: Policy) -> World {
        let ledger = Rc::new(MemLedger::default()); let head = Rc::new(Cell::new((0, 0))); let clock = Rc::new(Clock::default());
        let steps = Steps { ledger: ledger.clone(), head: head.clone() };
        steps.allow(1, "A"); steps.allow(1, "B"); steps.complete(1);
        steps.item(10, false); steps.item(11, false); steps.item(12, false);
        let data = Rc::new(Data {
            base: vec![row(1, 1, &[("A", Some(10))]), row(2, 1, &[("B", Some(11))]), row(3, 1, &[("B", None)]),
                       row(4, 1, &[("B", None)]), row(5, 1, &[("B", Some(13))])],
            delta: vec![row(4, 2, &[("B", Some(12))])],
            edges: vec![row(1, 1, &[("B", Some(12)), ("A", Some(10))]), row(3, 1, &[("B", Some(12)), ("B", None)])],
            index: RefCell::new(vec![]),
        });
        let view = Rc::new(ExclusionView { ledger: ledger.clone(), head, clock: clock.clone(), max_age: 30, policy, snap: RefCell::new(None) });
        let paid = PaidTier { view: view.clone(), data: data.clone(), steps: steps.clone() };
        paid.rebuild(1).unwrap();
        World { steps, paid, ledger, clock, view, data }
    }
    /// Cycle 2 allows only B and records A OptedOut (completed); item 11 Reserved.
    pub fn withdraw(&self) { self.steps.opt_out(2, "A"); self.steps.allow(2, "B"); self.steps.complete(2); self.steps.item(11, true); }
    pub fn tiers_ex(&self) -> &ExclusionView { &self.view }
    pub fn last_seq(&self) -> u64 { self.ledger.log.borrow().len() as u64 }
    pub fn has(rows: &[Row], src: Src, item: Option<u32>) -> bool {
        rows.iter().any(|r| r.inputs.iter().any(|(s, i)| *s == src && (item.is_none() || *i == item)))
    }
    /// A row of A, of reserved item 11 or of item 13 (no verdict).
    pub fn served_withdrawn(rows: &[Row]) -> bool { Self::has(rows, "A", None) || Self::has(rows, "B", Some(11)) || Self::has(rows, "B", Some(13)) }
}

#[cfg(feature = "composition-root")]
pub struct Authorities;
#[cfg(feature = "composition-root")]
impl Authorities { pub fn forged(&self) -> bool { true } }
#[cfg(feature = "composition-root")]
pub fn compose() -> Authorities { Authorities }

// ------------------------------------------------------------------ the round-6 shape, for the "before" runs
pub mod old {
    use super::*;
    /// The round-6 scope: a copy of the predicate taken at mint, served until `ttl`.
    pub struct OldScope { pub allow: HashSet<Src>, pub deny_items: HashSet<u32>, pub minted_at: u64, pub ttl: u64 }
    impl OldScope { fn admits(&self, r: &Row) -> bool { r.inputs.iter().all(|(s, i)| self.allow.contains(s) && i.map_or(true, |i| !self.deny_items.contains(&i))) } }
    pub struct OldStamp { rows: Vec<Row> }
    /// Item reservations kept as an unrecorded deny-list a store can lose.
    #[derive(Default)]
    pub struct ItemStore { pub reserved: RefCell<HashSet<u32>> }
    pub fn paid(w: &World, items: &ItemStore) -> OldScope {
        let log = w.ledger.log();
        OldScope { allow: allows(&log, newest_cycle(&log)), deny_items: items.reserved.borrow().clone(), minted_at: w.clock.0.get(), ttl: 30 }
    }
    pub fn build(w: &World, sc: &OldScope) -> OldStamp { OldStamp { rows: merged(&w.data).into_iter().filter(|r| sc.admits(r)).collect() } }
    pub fn search_stamp(st: &OldStamp) -> HubResult<Vec<Row>> { Ok(st.rows.clone()) }
    pub fn search_scope(w: &World, sc: &OldScope, st: &OldStamp) -> HubResult<Vec<Row>> {
        if w.clock.0.get() - sc.minted_at > sc.ttl { return Err(ErrorKind::StaleStamp); }
        Ok(st.rows.iter().filter(|r| sc.admits(r)).cloned().collect())
    }
    /// `table`, `union`, `merged`: the predicate is applied once, when the provider is created; statistics are exact.
    pub struct CopiedProvider { rows: Vec<Row> }
    impl Provider for CopiedProvider { fn scan(&self) -> HubResult<Vec<Row>> { Ok(self.rows.clone()) } fn statistics(&self) -> Option<usize> { Some(self.rows.len()) } }
    pub fn table(w: &World, sc: &OldScope) -> Box<dyn Provider> { Box::new(CopiedProvider { rows: merged(&w.data).into_iter().filter(|r| sc.admits(r)).collect() }) }
    /// A raw provider over the products, as `CREATE EXTERNAL TABLE` registers one.
    pub fn external(w: &World) -> Box<dyn Provider> { Box::new(CopiedProvider { rows: merged(&w.data) }) }
    pub struct CallerSession { pub tables: Vec<Box<dyn Provider>> }
    /// A deny-list derived from the catalog: a lost publish record drops the source from the list.
    pub fn catalog_scope(catalog_sources: &[Src], opted_out: &[Src]) -> OldScope {
        let all: HashSet<Src> = ["A", "B"].into_iter().collect();
        let deny: HashSet<Src> = catalog_sources.iter().filter(|s| opted_out.contains(s)).cloned().collect();
        OldScope { allow: all.difference(&deny).cloned().collect(), deny_items: HashSet::new(), minted_at: 0, ttl: 30 }
    }
    /// Round-4 refresh: extends the held index under the held predicate.
    pub fn refresh(w: &World, held: &OldScope, st: &mut OldStamp) {
        st.rows.retain(|r| !w.data.delta.iter().any(|d| d.key == r.key));
        st.rows.extend(w.data.delta.iter().filter(|r| held.admits(r)).cloned())
    }
    /// A guard below the merge: filters base and delta leaves, then merges.
    pub fn filter_then_merge(w: &World) -> Vec<Row> {
        let p = derive(Policy::R1, &w.ledger.log(), 1).unwrap();
        let d = Data { base: w.data.base.iter().filter(|r| p.admits(r)).cloned().collect(), delta: w.data.delta.iter().filter(|r| p.admits(r)).cloned().collect(), edges: vec![], index: RefCell::new(vec![]) };
        merged(&d)
    }
    /// Edges filtered on the edge row's own input only (no endpoint check).
    pub fn neighbours_edge_only(w: &World) -> Vec<Row> {
        let p = derive(Policy::R1, &w.ledger.log(), 1).unwrap();
        w.data.edges.iter().filter(|r| p.input(&r.inputs[0])).cloned().collect()
    }
    /// A crop rendered from the kept artefact by key, without the gate.
    pub fn crop(w: &World, key: u32) -> HubResult<Row> { merged(&w.data).into_iter().find(|r| r.key == key).ok_or(ErrorKind::NotFound) }
}
