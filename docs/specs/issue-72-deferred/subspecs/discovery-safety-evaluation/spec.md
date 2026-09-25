# Subspec: Discovery safety and evaluation

## Scope
Prove that discovery is metadata-only and preserves the local authority boundary.

## Requirements
- FR-3

## Acceptance criteria
1. WHEN discovery is called THEN no registered executor SHALL execute and registry state SHALL remain unchanged.
2. WHEN Hidden or Direct tools are present THEN neither SHALL appear in the Deferred discovery result.
3. WHEN the same registry is discovered repeatedly THEN the returned metadata/order/truncation state SHALL be stable.
4. WHEN tested on Windows 2025 and Ubuntu 24.04 THEN focused registry tests and the relevant local-agent full test suite SHALL pass.

## Files
- `services/local-agent/src/registry_tests.rs`
- production files only if required by the catalog contract

## Not included
No new authority, capability, policy, network, process, or persistence behavior.
