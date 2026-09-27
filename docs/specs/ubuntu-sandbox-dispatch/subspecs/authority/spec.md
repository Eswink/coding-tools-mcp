# 子规格：Native authority and retained workspace

## 范围

Native host integration owned by authority; production implementation remains blocked this turn.

## 需求回链

- FR-1
- FR-2
- FR-3

## 验收标准（EARS）

FR-1: WHEN a request lacks the approved conversation/workspace/scopes THEN the host SHALL deny it before any child process or sandbox policy can authorize it.

FR-2: WHEN the workspace is admitted THEN the host SHALL bind its retained directory object to the execution domain; replacement paths and symlinks SHALL NOT change the approved object.

FR-3: WHEN revocation, expiry, pause or a new boot wins before dispatch commit THEN the host SHALL reject stale tickets; committed work SHALL retain the existing draining and no-replay contract.

## 涉及文件

See parent design.md for the actual dispatcher and constructor paths; no production edit is authorized by this document.

## 不做项

No physical-host testing, cloud-minted local grants, model-controlled disable switches or production rollout.

## 设计要点

Follow the immutable workspace and one-use native permit contract in the parent design.
