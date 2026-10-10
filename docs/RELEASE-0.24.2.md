# Release 0.24.2

Completed the next P1 code task: regression tests for the current closed boundary between source data and planning. Job creation now rejects unsupported fields instead of silently ignoring them. No schema migration, dependency, or execution-action changes.

Seventeen new tests cover email/web/document/tool-output exclusion, job API source/control-field rejection, and model output action/authority rejection. Full suite: **116 passed, 1 warning**. Detailed limits and future connector gates: UNTRUSTED_DATA.md.

External content is still excluded from planning. The TODO retains the separate gate for real connector integration tests and live device acceptance.
