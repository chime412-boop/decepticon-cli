# Phase 4 — recovery and reconciliation

Acceptance criteria:
1. Intent without outcome is never retried blindly.
2. recovery_plan marks unresolved intent as READBACK_REQUIRED.
3. Positive read-back records/repairs outcome and reconciles the effect.
4. Negative read-back marks SAFE_TO_RETRY.
5. Retry cannot be authorized without SAFE_TO_RETRY.
6. Unknown read-back remains unresolved.
7. Recovery checks are durable and auditable.
8. All previous phase tests remain green.
