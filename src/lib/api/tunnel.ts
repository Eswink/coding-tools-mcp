import { invoke } from "@tauri-apps/api/core";
import { trackConfigurationChange } from "$lib/runtime/configuration";

export type TunnelService = "mcp" | "actions";

export interface TunnelStatus {
  state: string;
  publicUrl: string;
  tunnelPid: number | null;
}

export async function getFrpSnippet(id: string, service: TunnelService): Promise<string> {
  return invoke<string>("get_frp_snippet", { id, service });
}

export async function startTunnel(id: string, service: TunnelService): Promise<TunnelStatus> {
  return trackConfigurationChange(() => invoke<TunnelStatus>("start_tunnel", { id, service }));
}

export async function stopTunnel(id: string, service: TunnelService): Promise<TunnelStatus> {
  return trackConfigurationChange(() => invoke<TunnelStatus>("stop_tunnel", { id, service }));
}

export interface TunnelTestResult {
  success: boolean;
  publicUrl: string;
  keptRunning: boolean;
  message: string;
}

export async function testTunnel(id: string, service: TunnelService): Promise<TunnelTestResult> {
  return trackConfigurationChange(() => invoke<TunnelTestResult>("test_tunnel", { id, service }));
}

export async function restartTunnel(id: string, service: TunnelService): Promise<TunnelStatus> {
  return trackConfigurationChange(() => invoke<TunnelStatus>("restart_tunnel", { id, service }));
}
