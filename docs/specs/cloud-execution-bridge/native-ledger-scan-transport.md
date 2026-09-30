# Native ledger scan transport

## Observed regression

Diagnostic run [36721401856](https://github.com/Eswink/coding-tools-mcp/actions/runs/36721401856)
at the preceding source observed persisted scans taking 842–910 ms for 35–38
inactive ledgers. Approximately 99% was measured in system-key reads. Serial
root admission took 3.4 seconds while the tool body took 4–117 ms. Two original
`exec_input_contract` end-to-end assertions therefore exceeded their unchanged
three-second limit. This is admission overhead, not evidence of a blocked pipe.

## Bounded change

Each `persisted_conflict` scan owns an `AuthDocumentReader`. On production Linux
it lazily opens one encrypted Diffie–Hellman Secret Service session. Every ledger
still searches the current system service and obtains its key afresh, takes its
existing file lock, reads the current bounded ciphertext, verifies namespace
binding and AES-GCM authentication, and applies the unchanged conflict rules.
No credential, item handle, search result or decoded document is cached. The
reader is dropped when the scan returns, including every error return. A failure
never triggers a reconnect, alternate backend, unlock, prompt or credential write
within that scan. Empty scans do not contact Secret Service.

The attribute lookup preserves keyring 3.6.3: first service-wide exact
`service` + `username` + `target=default`; only if that finds no items, search
`service` + `username` in the default collection. Exact matches take precedence.
Locked or ambiguous results fail closed, including an unlocked match alongside
a locked duplicate. Compatibility fallback cannot search other collections.

Existing macOS/Windows providers and normal credential writes are unchanged.
The registry lock, 512-ledger bound, file checks, ledger schema, root identity,
durable phase rules and process deadlines are unchanged. The graph impact is
HIGH: four direct callers, fourteen impacted symbols, three execution flows.
Rust method-resolution and unavailable FTS limit the graph's completeness.

## Verification gates

- Deterministic authenticated-document regression rereads keys on every load,
  rejects deletion/rotation/provider failure and modified ciphertext, and sees
  new authenticated record contents without reopening its document.
- `native-keyring-tests` explicitly exercises the real scan adapter: current
  keys, deletion, rotation, duplicate exact and legacy matches, exact precedence,
  default-only fallback, missing keys, denied writes and ciphertext corruption.
- A separate mandatory hosted fixture owns a disposable D-Bus, keyring daemon,
  home and random credentials. It proves locked/unlocked duplicate rejection,
  service disconnection, expired session after restart, fresh-session recovery,
  and bus loss. Both Ubuntu workflows select each of the three ordinary key
  regressions by its fully qualified exact name, then run the lifecycle test's
  exact name only through the owned fixture. Every selected test must print its
  named PASS line. The lifecycle test is never ignored; invocation without its
  private fixture fails before touching a service.
- Diagnostic CI repeats all six original stdin contracts three times, with
  their original concurrency and three-second assertions, in both fresh and
  preceding-suite-populated stores. Errors are retained across later suites.
- Complete native regression and production warning gates remain required.

Local native-feature compilation and the deterministic regression passed in the
Dot executor. Real D-Bus startup is denied there by socket policy, so service
fault injection and loaded latency are pending hosted proof, not a local pass.
