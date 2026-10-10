# Design: fixed manager raw checkout

## 概述
Versioned seven literal `-text` attributes suppress EOL conversion for existing raw manager source identity. Full strict verifier stays exact. Git configuration origin is UNKNOWN; actualLFtoCRLF physical pattern is established by realCI diagnostic hashes, counts and IDs.

## 技术方案
Root `.gitattributes` lists only the seven existing manager lease source names from originalguard. It changes no source body or global config. Existing original SUTrestore already uses command-scoped `core.autocrlf=false`, separate --no-checkout clone, localfalse, BASEcheckout and customindex checkout-index; this remains unmodified and requires WindowsCI.

## Data Flow
Native Git HEAD raw blobs -> ordinary Git checkout with true/false EOL setting -> seven literal -text attributes preserve raw bytes -> actual unchanged verify_manager. Mutation follows existing failure branch. An unmatched ordinary fixture proves broader checkout policy is unchanged.

## Error Handling
Absent/invalid/mutated source remains original raw verification failure. Attribute/check-out control failure is a source-only failure, never an owner or compiler proof. No post-checkout normalization is used.

## FR Coverage Matrix
| Requirement | Source | Evidence |
| --- | --- | --- |
| FR-1 | .gitattributes | exactliteral7 parse and nativecheck-attr |
| FR-2 | originalguard unchanged | actualfullguard rawPASS andmutationFAIL |
| FR-3 | ordinaryownedGitcontrols | actualclone true/false/noattrs/counterexample |
| FR-4 | independentidentity andpeer | baseline1862 unchanged/new5 sourceonly |

## 文件结构
Five new paths only: .gitattributes; scripts/windows_foundation_manager_checkout_tests.py; requirements/design/tasks in this spec directory. No existing source changes.
