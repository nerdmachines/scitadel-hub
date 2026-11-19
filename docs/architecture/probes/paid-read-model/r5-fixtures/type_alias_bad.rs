// R5 fixture: a `pub type` alias re-exports a provider type; the check must reject it.
pub type ArrowBatch = arrow::record_batch::RecordBatch;
pub type Ctx = datafusion::prelude::SessionContext;
