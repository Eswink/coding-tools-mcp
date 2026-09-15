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
  reasonCode: string | null;
  message: string;
  platform: string;
  safeMode: boolean;
}

export interface PlatformContext {
  os: string;
  family: string;
  arch: string;
  distribution: string | null;
  pathStyle: string;
  pathSeparator: string;
  caseSensitivePaths: boolean;
  executableSuffix: string;
  defaultShell: string;
  shellModes: string[];
  commandExecution: string;
  commandGuidance: string;
}

export interface EnvironmentDiagnostics {
  appVersion: string;
  packageKind: string;
  platform: PlatformContext;
  safeMode: boolean;
  diagnoseStartup: boolean;
  displayBackend: string;
  desktopSession: string;
  sessionBusConfigured: boolean;
  credentialStoreState: string;
  startupFailureReason: string | null;
  configurationState: string;
  configurationExists: boolean;
  configurationEncrypted: boolean | null;
  configurationOwnedByCurrentUser: boolean | null;
  configurationOwnerOnlyPermissions: boolean | null;
  configurationDirectoryWritable: boolean | null;
  trayAvailable: boolean;
  notificationPluginEnabled: boolean;
  executables: Record<string, boolean>;
}

export async function getStartupStatus(): Promise<StartupStatus> {
  return invoke<StartupStatus>("get_startup_status");
}

export async function retryStartup(): Promise<StartupStatus> {
  return invoke<StartupStatus>("retry_startup");
}

export async function getEnvironmentDiagnostics(): Promise<EnvironmentDiagnostics> {
  return invoke<EnvironmentDiagnostics>("get_environment_diagnostics");
}
