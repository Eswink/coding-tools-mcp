# One-shot reviewed source recovery for #41 / #36

This independent CI branch restores two reviewed local commits when the connector cannot accept a Git bundle directly. It is NOT a feature or deployment branch and must never be merged.

The 12 binary parts are an XZ-compressed JSON record of source patches and commit metadata only. They contain no dependency/toolchain binaries or credentials. Concatenate in numeric order; SHA-256 must be `536c414e8466f8acd21f4dd03f2bfe2f99c09b2eccb01a885f19e26c66b1c282` (68520 bytes). Base `ba9c379f08da37f2a05bb96c377a95f432da969e`; target `5b55ba5eaaaea11d8c2322bbaa5980980cc8ad48`; exact target source tree `92ea0acab1281db6feb85f02c14290235eabff3e`.

The read-only verification job reconstructs and checks both source trees and reruns actual PostgreSQL/HTTP/Rust and prior contract tests. Only a dependent object-import job receives a write token, solely for creating Git blob/tree/commit objects. The script NEVER updates a branch ref. Publication is separately reviewed and fast-forwarded through the authenticated connector after the receipt is checked. Concurrent remote changes fail closed. Main, desktop, releases, DNS and VPS are untouched.
