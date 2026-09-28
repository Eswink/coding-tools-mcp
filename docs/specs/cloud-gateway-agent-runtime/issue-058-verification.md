# ISSUE-058 verification receipt

Feature source: `4196b702b9c13debfd73fabe54c571c99bb14cd7`.
Native lab run 35770305269 succeeded: Windows 2025 job 106890040038,
Ubuntu 24.04 job 106890040423, and pinned graph/spec job 106890040417.
Both OS jobs passed actual scope verification, protocol/scope tests and existing
offline-safe regressions. Issue #58 was closed after this verification.

Earlier runs remain failures: 35767741738 exposed the test's CRLF extraction;
35768825077 exposed WinError 32 because cwd was still inside TemporaryDirectory
when cleanup began. The final fixture uses contextlib.chdir to restore cwd before
cleanup, including exceptions. No cleanup exception is ignored and no test skipped.
The exact origin-migration allowlist entry remains the only guard-policy change.

Local protocol/scope suite: 49 tests passed. Neither this receipt nor the native
CI result certifies installed hosts, security review, packages or real ChatGPT.
Main, production deployment and formal releases remain untouched.
