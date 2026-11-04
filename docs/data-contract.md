# Data contract

Every financial value must include company, metric, period, currency, unit, statement scope, source document, source page or span, extraction method and quality status. A missing value is `null` with a reason. A derived value stores its formula and all input evidence IDs.

A document is identified by source identifier and SHA-256. Re-ingestion is idempotent. Historical analysis filters documents by `published_at <= as_of`.
