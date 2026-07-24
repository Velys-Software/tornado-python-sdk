---
name: tornado-api-repo
description: The Rust API source that this Python SDK targets lives at /Users/alex/Developer/velys/TornadoAPI (axum; routes in src/main.rs ~line 1073, handlers in src/api/)
metadata:
  type: reference
---

The Tornado API (server side) is a Rust/axum service at `/Users/alex/Developer/velys/TornadoAPI`.
Key entry points for SDK-vs-API comparisons:
- Routes: `src/main.rs` (~line 1073: api_routes, user_routes, admin_routes, public_routes)
- Request/response types: `src/api/types.rs`
- Handlers: `src/api/jobs.rs` (create/get/list/cancel/retry), `src/api/batch.rs` (bulk + Spotify batches), `src/api/storage.rs`, `src/api/admin.rs` (get_usage)
- Job status enum: `src/database/types.rs` (Pending/Processing/Completed/Failed/Warning/Skipped — **no Cancelled variant**)
- Inline storage enum: `src/marketplace.rs` (serde tag="provider", lowercase: s3/blob/gcs/oss)

**How to apply:** when reviewing or changing the SDK (`tornado-python-sdk`), verify against these files rather than the SDK's own docstrings — several SDK docstrings have drifted from the API.
