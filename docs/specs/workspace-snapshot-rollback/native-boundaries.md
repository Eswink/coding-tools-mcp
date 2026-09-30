# Native snapshot fixture boundaries

This branch tests bounded snapshots on disposable filesystem fixtures only. It registers no production snapshot approval or restore IPC route. Native runtime drain/admission integration is a separate required gate.

Linux source checks and fixtures have passed in the full Tauri test executable, including the existing ordinary-task no-copy regression. Windows source cross-checks compile for MSVC, but native runtime results must come from this branch's Windows job and exact-source receipt.

The Windows candidate records owner, group, DACL, mandatory-integrity label and supported file attributes. It never enables privileges, changes original preimage ACLs, grants broad access or drops inherited-control flags to force a pass. Audit SACL preservation is not implemented: reading it requires ACCESS_SYSTEM_SECURITY and a currently enabled security privilege. Full-metadata production rollback must remain blocked pending a supported object-preserving design or a complete fail-closed capability path. Default-fixture DACL success is not proof of SACL preservation.

The Linux increment records mode bits; UID/GID binding and fail-closed extended-attribute handling are being hardened separately. Files with unsupported ownership, ACL, capability, label or other metadata must not be silently copied with that metadata lost. These are engineering blockers, not deferred physical-host acceptance.

Partial transactions retain displaced content and refuse further mutation after restart. External editors are not assumed quiescent. Neither a broker mutex nor canonical path alone grants restore authority. Owner confirmation and proven native drain are required for any future production restore path.

Sources: [GetSecurityInfo](https://learn.microsoft.com/en-us/windows/win32/api/aclapi/nf-aclapi-getsecurityinfo), [SetSecurityInfo](https://learn.microsoft.com/en-us/windows/win32/api/aclapi/nf-aclapi-setsecurityinfo), [CreateFile sharing semantics](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew).
