# Design

## 概述

Corresponding FR-1..FR-5. Minimalnewtest/proposal only. Reuse exact existing Go methods: createGuestWorkspaceOutput, openInto, checkParent/checkPin, freeze/wire, closeKnown andguestRawInfo; originalproduction implementations remain immutable.

## 技术方案

New Windows-only testfile adds independent ownedfixture helper with realtempdirectory creation, actual native directoryhandle and identity observation; it never constructs applicationpermission/VMowner. Reuse original9fields streamfixture as data. Parentpin control opens callerparent withshare7, checks actualDELETE-access handle works before and afteroutputparentpin and failsduring it, to avoid falsely attributing transitivefilepin denial. Exclusivecreate/hardlink/reparse controls verify unchangedcanary bytes and object/volumeIDs. Unknownclose sets and reads back actual HANDLE_FLAG_PROTECT_FROM_CLOSE on the live owned read handle before the original closeKnown call; this prevents the invalidated-number/reuse race. It forbids retry/reuse or clearing the protection after an uncertain result, holds existingstrong outputregistry/pins/bytes and marksfixtureuncertain so cleanupwillnotRemoveAll. RealWinAPI fault injection is stated separately from productionfault; noPOSIXfake proof.

CIproposal uses a dedicated actual Windows jobsource fetched and frozen independently from managementcarrier; no blindGITHUB_SHA substitution forSUT source. Emit go test -list exactIDs before execution, compile frozen source, then go test -json -count=1 -tags=guest with exactoriginal9/newcontrols allowlist and requiredordinarynativeinput support. Fullraw event vectors/naturalownedtestprocessclosure and aftercanaries must be preserved; noSkip/0count admits. Symlink/NTFS/rights shortage is explicitBLOCKED/FAIL. ProposedCI is NOTRUN and cannot be reported as actualworkflow execution.

## 文件结构

New services/windows-vm-broker/guest_workspace_output_nt_boundary_native_test.go only; docs/specs/windows-nt-output-boundary-native-controls/{requirements,design,tasks}.md and source/hash/CIproposal safe manifests. No production/Rustmod/owner/gate changes.
