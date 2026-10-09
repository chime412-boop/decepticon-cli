# Phase 5 — verified skills

book-to-skill is available in D:\IMPLEMENTAR SI O SI\book-to-skill.

Acceptance criteria:
1. A generated skill is imported from a directory containing SKILL.md.
2. Content is fingerprinted with SHA-256.
3. Same name/version cannot silently change content.
4. Unverified skills cannot be activated.
5. Verification re-reads the manifest and rejects post-registration mutation.
6. Verified skills can be activated per project/machine.
7. All earlier phase tests remain green.
