// A caller passes a stamp it kept to the paid gate (history: a held stamp).
fn main() {
    let w = boundary::World::new();
    let stamp = w.paid.rebuild(1).unwrap();
    let _ = w.paid.search(&stamp, "q"); // E0308: search takes a GenerationRef, never a stamp
}
