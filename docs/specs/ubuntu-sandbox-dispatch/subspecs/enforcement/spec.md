# 子规格：Mandatory child-process isolation

## 范围

Native host integration owned by enforcement; production implementation remains blocked this turn.

## 需求回链

- FR-4
- FR-5

## 验收标准（EARS）

FR-4: WHEN an approved Linux Process or TTY request reaches spawn THEN the host SHALL attach the required sandbox, or return SANDBOX_REQUIRED/SANDBOX_SETUP_FAILED before exec. Omitted policy SHALL NOT select legacy unsandboxed execution.

FR-5: WHEN model arguments try sandbox=false or disable_sandbox=true THEN the host SHALL reject the unsupported fields or enforce isolation independently. Working-directory, filesystem and network constraints SHALL NOT be relaxed by those values.

## 涉及文件

See parent design.md for the actual dispatcher and constructor paths; no production edit is authorized by this document.

## 不做项

No physical-host testing, cloud-minted local grants, model-controlled disable switches or production rollout.

## 设计要点

Follow the immutable workspace and one-use native permit contract in the parent design.
