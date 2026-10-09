# Phase 7 — supervisor and crash recovery E2E

Acceptance criteria:
1. Supervisor derives ACTIVE/IDLE/CRASHED from heartbeat age.
2. CRASHED session receives ended_at and unfinished owned tasks become ORPHANED.
3. Every orphaned task produces a durable P0 alert.
4. Another live session can take over the orphaned task.
5. Completion still requires VERIFIED_E2E.
6. A real killed child process is used in the adversarial test.
7. CLI exposes supervisor, alerts and status snapshot.
8. All previous phase tests remain green.
