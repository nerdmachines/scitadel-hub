// A caller reaches into a paid session for its context to keep or cache (history: register into a caller-kept SessionContext).
fn main() {
    let w = boundary::World::new();
    let s = w.paid.session(1).unwrap();
    let _ctx = s.ctx; // E0616: private field
}
