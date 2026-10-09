# Phase 6 — process adapters

Acceptance criteria:
1. Processes are declarative specs, not hard-coded business logic.
2. Specs default disabled.
3. dry_run resolves cwd/argv/readback without execution.
4. Real execution records side-effect intent before launch.
5. Exit result is durable; read-back decides reconciliation.
6. VERIFIED_E2E requires exit 0 plus successful read-back.
7. Catalog includes Oportunidades and PAY entrypoints discovered on laptop.
8. Redes is not given a fake executor when none was found.
9. All earlier tests remain green.
