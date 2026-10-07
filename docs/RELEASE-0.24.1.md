# Release 0.24.1

The next code item from the prioritized TODO is the initial credential/OAuth review. Findings and remaining production gates are in SECURITY_REVIEW.md.

Fixed parsed loopback redirect validation, refreshed read-scope validation, encrypted refresh-token rotation, and conditional token persistence when the connection changes during refresh. Initial consent now rejects unexpected scopes. No schema or dependency changes.

Full suite: 99 passed, 1 existing deprecation warning. Live Windows/Chromebook checks and Google/PostgreSQL concurrency remain unverified. The next priority remains target-device acceptance, followed by untrusted-input isolation and the open production gates.
