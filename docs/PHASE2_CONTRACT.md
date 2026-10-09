# Phase 2 — session lifecycle and ownership

Acceptance criteria:
1. Heartbeat refreshes a live session.
2. Sessions become IDLE when heartbeat exceeds the active window.
3. ENDED and CRASHED are explicit terminal session states.
4. A task cannot be stolen from an ACTIVE owner without force.
5. A task owned by an ended/crashed session can be taken over.
6. Every claim/takeover is durably recorded in task_claims.
7. catch_up_audit marks unfinished work ORPHANED when its owner is terminal.
8. All Phase 1 tests remain green.
