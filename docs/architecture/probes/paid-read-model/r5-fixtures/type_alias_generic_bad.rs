// R5 fixture: a `pub type` alias with the provider type inside generics; the check must reject it.
pub type Provider = Arc<dyn datafusion::catalog::TableProvider>;
