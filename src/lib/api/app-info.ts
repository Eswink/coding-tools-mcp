import { invoke } from "@tauri-apps/api/core";

export interface UpdateCheckResult {
  currentVersion: string;
  latestVersion: string;
  latestTag: string;
  updateAvailable: boolean;
  releaseUrl: string;
}

export async function openUrl(url: string): Promise<void> {
  return invoke("open_url", { url });
}

export async function checkAppUpdate(): Promise<UpdateCheckResult> {
  return invoke<UpdateCheckResult>("check_app_update");
}

export interface StartupStatus {
  state: "ready" | "locked" | string;
  ready: boolean;
  recoverable: boolean;
  message: string;
  platform: string;
}

export async function getStartupStatus(): Promise<StartupStatus> {
  return invoke<StartupStatus>("get_startup_status");
}

export async function retryStartup(): Promise<StartupStatus> {
  return invoke<StartupStatus>("retry_startup");
}
