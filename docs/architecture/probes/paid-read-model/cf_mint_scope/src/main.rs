// A caller tries to hold a paid scope of its own (history: a held `Scoped` within its TTL).
fn main() {
    let w = boundary::World::new();
    let _s = boundary::Scoped::mint(&w.tiers_ex(), 1); // E0624: private to hub-boundary
}
