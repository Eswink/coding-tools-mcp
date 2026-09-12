import { invoke } from "@tauri-apps/api/core";
import { trackConfigurationChange } from "$lib/runtime/configuration";
import type { RuntimeStatus, WorkspaceProfile } from "$lib/types";

export async function listWorkspaces(): Promise<WorkspaceProfile[]> {
  return invoke<WorkspaceProfile[]>("list_workspaces");
}

export async function createWorkspace(
  path: string,
  name?: string,
): Promise<WorkspaceProfile> {
  return trackConfigurationChange(() => invoke<WorkspaceProfile>("create_workspace", { path, name }));
}

export interface TunnelSecretUpdate {
  key: "cloudflare_token" | "frp_token" | "actions_cloudflare_token" | "actions_frp_token";
  value: string;
}

export async function updateWorkspace(profile: WorkspaceProfile, tunnelSecret?: TunnelSecretUpdate): Promise<void> {
  return trackConfigurationChange(() => invoke<void>("update_workspace", { profile, tunnelSecret }));
}

export async function openWorkspaceDirectory(path: string): Promise<void> {
  return invoke("open_workspace_directory", { path });
}

export async function deleteWorkspace(id: string): Promise<void> {
  return trackConfigurationChange(() => invoke<void>("delete_workspace", { id }));
}

export async function startRuntime(id: string): Promise<RuntimeStatus> {
  return trackConfigurationChange(() => invoke<RuntimeStatus>("start_runtime", { id }));
}

export async function stopRuntime(id: string): Promise<RuntimeStatus> {
  return trackConfigurationChange(() => invoke<RuntimeStatus>("stop_runtime", { id }));
}

export async function getRuntimeStatus(id: string): Promise<RuntimeStatus> {
  return invoke<RuntimeStatus>("get_runtime_status", { id });
}

export async function startActionsRuntime(id: string): Promise<RuntimeStatus> {
  return trackConfigurationChange(() => invoke<RuntimeStatus>("start_actions_runtime", { id }));
}

export async function stopActionsRuntime(id: string): Promise<RuntimeStatus> {
  return trackConfigurationChange(() => invoke<RuntimeStatus>("stop_actions_runtime", { id }));
}

export async function getActionsRuntimeStatus(id: string): Promise<RuntimeStatus> {
  return invoke<RuntimeStatus>("get_actions_runtime_status", { id });
}

export async function restartRuntime(id: string): Promise<RuntimeStatus> {
  return trackConfigurationChange(() => invoke<RuntimeStatus>("restart_runtime", { id }));
}

export async function restartActionsRuntime(id: string): Promise<RuntimeStatus> {
  return trackConfigurationChange(() => invoke<RuntimeStatus>("restart_actions_runtime", { id }));
}
