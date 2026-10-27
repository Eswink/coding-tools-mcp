# Requirements: bounded publication executor

## 功能概述
Implement the concrete execution, HTTPS transport and owned staging needed by the existing Issue88 publication core. This engineering increment runs real local protocol tests; current missing authentic eligibility and existing-tag-only guarantees keep production publication blocked.

## 需求列表
### FR-1 Fixed production admission (Must)
WHEN any production entry or mutation is requested, the implementation SHALL consult fixed current authenticators and reject unsupported eligibility and existing-tag-only guarantees before mutation bytes. Caller booleans, callbacks, records, environment and PublicationRequest SHALL not grant authority. Policy, eligibility and the inert core SHALL remain unchanged.
### FR-2 Core-driven owned session (Must)
WHEN dispatching, one in-memory session SHALL execute only the unchanged core's outstanding operation, at most once, without concurrent/reentrant dispatch, retries or state import. The 25-operation sequence SHALL pause with owned handles until an exact explicit request. Closing an idle pause SHALL close local lifetime without inventing a core operation/outcome or resuming.
### FR-3 Exact selected receipts and assets (Must)
WHEN preparing staging, the implementation SHALL authenticate exact source, consumer/FINAL/integration runs, attempts, jobs and artifact metadata/bytes, reconsume the exact FINAL archive through existing validation, preserve original plan/provenance bytes, and stage exactly six fixed assets. It SHALL not spoof consumer invocation, select another run or transfer paths from closed consumer roots.
### FR-4 Byte and lifetime integrity (Must)
WHILE a session exists, it SHALL retain private root contexts and nofollow regular read handles, recheck identity/membership/hash at fences, and count/hash the same streamed upload bytes. Replacement, links, drift, missing bytes and uncertain cleanup SHALL fail; the existing no-concurrent-same-UID-writer assumption remains explicit.
### FR-5 Bounded closed HTTPS operations (Must)
WHEN contacting GitHub, handlers SHALL construct only fixed repository operations, verify TLS, reject metadata redirects, bound complete pagination/headers/body/deadlines, and permit at most one exact credential-free storage redirect for binary reads. Anonymous final metadata and byte verification SHALL contain no credentials. Typed absence SHALL require authentic visibility, never an unqualified 404.
### FR-6 Failure, cancellation and verification (Must)
WHEN dispatch is possible without a complete matching mutation success, the result SHALL remain unknown and terminal. Pre-dispatch failure SHALL be no-effect; confirmed success followed by cleanup failure SHALL retain known IDs. Every mutation SHALL recheck current owner scope/cancellation immediately before writing. Final success SHALL require exact anonymous bytes, stable/latest identity and successful local cleanup; raw bodies/tokens/URLs SHALL not escape errors.
### FR-7 Finite source admission (Must)
WHEN selecting this extension, the profile SHALL accept only D[M], I[M,D] with D's complete tree, and J[R,I] with the exact four R documents. It SHALL freshly validate immutable M, require every exact path/mode/pin/budget, and reverse the sole four-line dispatcher change byte-for-byte. Content/historical failures SHALL be terminal; only topology mismatch delegates.
### FR-8 Real tests and preserved boundaries (Must)
The increment SHALL preserve all original1184/strict303 cases and add exactly48 named cases, including real loopback TLS serialization/streams and negative ownership/admission/ambiguity paths. New CI SHALL have read-only permissions, exact source admission, Ubuntu22/24 Python3.12 and no live credentials or mutation. Required context coverage is D1232/I893/J893; no skipped or exceptional outcomes qualify.

## 非功能需求
Fourteen paths, thirteen additions, one replacement, all100644, 1745 entries and aggregate delta<=3400. Individual caps are declared in design. No new dependencies. Header/body/page/archive/stream limits are explicit; cooperative deadlines do not claim forced interruption of synchronous DNS/kernel calls.

## 依赖关系
Reuse rc_publication_contract, rc_consumer_io/snapshot/archive/transport, _verify_bundle_bytes and historical composition unchanged. Production activation still needs real authenticating gate producers and a remote existing-tag-only guarantee. Windows isolation, snapshot implementation, held PR98 ref/payload, final release and credential/security changes remain outside this increment.
