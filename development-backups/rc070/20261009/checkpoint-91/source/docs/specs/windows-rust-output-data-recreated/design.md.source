# Design: windows-rust-output-data-recreated

## 概述
FR1 output parser strictly validates bounded raw frames; FR2 Reader EOF and monotonic cancellation are data boundaries; FR3 ArcMutex owns once-consumable private data; FR4 source-specific graph and true isolated tools preserve honest evidence.

## 技术方案
OutputDataCancellation wraps private ArcAtomicBool; cancel_output_data only stores true, Default starts false. receive_output_data validates original RunBinding via input::owned_run existing alias, derives lengthprefix SHA, then reads bounded72byteheaders/body with checks around each read. Sequence0..32/body/nonempty/final/offsettotal/reserved/hash/binding are exact. No data escapes before zero-body final plus actual ReaderEOF; detached OutputDataTransfer shares all private state via ArcMutex. take_output_data locks sharedstate, marks consumed before every validation, checks cancel/binding/hash, clones≤1MiB then rechecks cancel. Poisonedmutex remainsdeny.

## Data Flow
Original same nominalRunBinding → digest/rawdirection2 input → boundedframe/hash/finalReaderEOF → private ArcMutex detacheddata → one terminal take returnsVec. No native proof/authorization object or connection to request_publication.

## Error Handling
Any parser/cancel/read/header/hash/EOF failure returns explicit data error and no owner. Any consumption attempt becomes terminal. No panic/unwrap in production code. Reader may synchronously block; token records stop but can't unblock IO, and test releases its own controlledordinaryreader. No timeoutgoroutine, fakeEOF, nativeclose or cancelledreaderabandonment claim.

## 文件结构
Only3Rust+3spec. data.rs≤250lines, data_tests.rs≤400lines, mod.rs only module registration. Minimalcratefacade lives outside sourcecheckout, path/includes point to unchanged actual originals; accurately reproduces only data needed aliases and no native owner functions. Original gate/nt/owner/input files remain exact. Existing output defaultdeny remains intact.

## FR Coverage Matrix
| Requirement | Source | Evidence |
| --- | --- | --- |
| FR-1 | data parser/digest | trueGo vectors/headers/binding/capacity/hash tests |
| FR-2 | cancellation/Read helpers | realReaderEOF/readfailure/controlledblock test |
| FR-3 | sharedstate/take | clone/32concurrent/foreignterminal/poison/mutation tests |
| FR-4 | moduleonly/sourcefreeze | actualpinnedRust tool leases/declaredfacade/allbaseblobidentity/peer |

## 测试策略
Generate actual Go golden cases with unchanged original transfer.go/workspace_stream.go/guest_workspace_control.go and current frozen output_transfer.go copied byte-exact into owned toolproject; actualGo outputsource hashes beforeafter. Rust uses exact original inputtransfer/path/chunks with literal facade for existing owned_run alias; dependencies from original lock sha2 0.10.9/uuid1.23.4. Actual runtimepayloadhash/version beforeafter and source allnativeblobs maintained. Tests target realbehavior, not mirrored implementation-only static checks. Golden small UTF8rawwire plus boundarywire SHA/computeddata hashes; real pure Go outputtake verified. No wholeWindowsnative proof.

## 风险评估
Original RunBinding freshownGN HIGH9/direct4/process1/modules3; no originalbodyedit. New symbols UNKNOWN, manualHIGH disclosed. Actual Read implementation can block; atomiccancel checks do not promise native cancellation or allIO retirement. Claimedfacade compile excludes productionnative owner/Tauri; exact sourceproject fullcompilation remains a later realWindows gate.
