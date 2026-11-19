//! A featureless crate whose doctest reaches `compose` only through workspace feature unification.
//!
//! ```
//! let a = boundary::compose();
//! assert!(a.forged());
//! ```
pub fn nothing() {}
