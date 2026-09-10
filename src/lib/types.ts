import { frpOrigin, normalizePublicOrigin, type FrpRouteOptions } from "./固定入口";

export type RuntimeState = "stopped" | "starting" | "running" | "stopping" | "error";

export const DEFAULT_SERVICE_PORT = 28766;
export const DEFAULT_ACTIONS_PORT = 8787;

export interface TunnelConfig {
  type: string;
  public_url: string;
  frp_server: string;
  frp_subdomain: string;
  frp_profile_id?: string;
  frp_server_port?: number;
  frp?: FrpRouteOptions;
  cloudflare_mode: string;
  cloudflare_http2?: boolean;
  use_proxy?: boolean;
}

export interface AuthConfig {
  type: string;
  oauth_client_id: string;
  oauth_redirect_uri?: string;
  use_shared_secrets?: boolean;
}

export interface RuntimeConfig {
  local_port: number;
  tool_profile: string;
  permission_mode: string;
  runtime_command?: string;
  max_task_timeout_ms?: number;
  allowed_commands?: string;
  workspace_local_entries?: boolean;
  workspace_script_extensions?: string;
}

export interface ActionsConfig {
  public_url: string;
  tunnel_type: string;
  frp_server: string;
  frp_subdomain: string;
  frp_profile_id?: string;
  frp_server_port?: number;
  frp?: FrpRouteOptions;
  cloudflare_mode: string;
  cloudflare_token?: string;
  cloudflare_http2?: boolean;
  use_proxy?: boolean;
  local_port: number;
  permission_mode: string;
  runtime_command?: string;
  max_task_timeout_ms?: number;
  auth_type: string;
  oauth_client_id?: string;
  oauth_scopes?: string;
  allowed_commands?: string;
  max_patch_bytes?: number;
  use_shared_secrets?: boolean;
}

export interface WorkspaceProfile {
  id: string;
  name: string;
  path: string;
  tunnel: TunnelConfig;
  auth: AuthConfig;
  runtime: RuntimeConfig;
  actions?: ActionsConfig;
}

export interface RuntimeStatus {
  state: RuntimeState;
  pid: number | null;
  localMessage: string;
  publicMessage: string;
  localEndpoint: string;
  publicEndpoint: string;
}

export function actionsConfig(profile: WorkspaceProfile): ActionsConfig {
  return {
    public_url: "",
    tunnel_type: "frp",
    frp_server: "",
    frp_subdomain: "",
    cloudflare_mode: "quick",
    cloudflare_http2: true,
    local_port: DEFAULT_ACTIONS_PORT,
    permission_mode: "trusted",
    auth_type: "api_key",
    allowed_commands:
      "pytest,python,python3,npm,npx,node,pnpm,yarn,make,mvn,mvnw,gradle,gradlew,cargo,go,ruff,mypy,eslint,tsc",
    max_patch_bytes: 200_000,
    ...profile.actions,
  };
}

export function mcpLocalEndpoint(port: number): string {
  return `http://127.0.0.1:${port}/mcp`;
}

export function actionsLocalEndpoint(port: number): string {
  return `http://127.0.0.1:${port}`;
}

export interface ActionsAuthDraft {
  authType: string;
  oauthClientId: string;
  oauthScopes: string;
  useSharedSecrets?: boolean;
}

export interface FrpProfileSummary {
  id: string;
  name: string;
  server: string;
  serverPort: number;
}

export function frpPublicUrl(
  tunnelType: string,
  frpSubdomain: string,
  frpServer: string,
  frpProfileId: string | undefined,
  profiles: FrpProfileSummary[],
  publicUrl = "",
  options?: Partial<FrpRouteOptions>,
): string {
  try {
    if (tunnelType !== "frp") return publicUrl ? normalizePublicOrigin(publicUrl) : "";
    const server = profiles.find((profile) => profile.id === frpProfileId)?.server ?? frpServer;
    return frpOrigin(server, frpSubdomain, options);
  } catch {
    // Invalid drafts must not advertise a fabricated public endpoint.
    return "";
  }
}

export function actionsPublicBaseUrl(
  profile: WorkspaceProfile,
  frpProfiles: FrpProfileSummary[] = [],
  activeOrigin?: string,
): string {
  if (activeOrigin !== undefined) {
    try { return activeOrigin ? normalizePublicOrigin(activeOrigin) : ""; }
    catch { return ""; }
  }
  const actions = actionsConfig(profile);
  // Temporary URLs are owned by the active listener, never by persisted config.
  if (actions.tunnel_type === "cloudflare" && actions.cloudflare_mode === "quick") return "";
  const publicUrl = frpPublicUrl(
    actions.tunnel_type,
    actions.frp_subdomain,
    actions.frp_server,
    actions.frp_profile_id,
    frpProfiles,
    actions.public_url,
    actions.frp,
  );
  if (publicUrl) return publicUrl;
  return actionsLocalEndpoint(actions.local_port);
}

export function actionsOpenApiUrl(
  profile: WorkspaceProfile,
  frpProfiles: FrpProfileSummary[] = [],
  activeOrigin?: string,
): string {
  const base = actionsPublicBaseUrl(profile, frpProfiles, activeOrigin);
  return base ? `${base.replace(/\/$/, "")}/openapi.json` : "";
}

export function actionsPrivacyUrl(
  profile: WorkspaceProfile,
  frpProfiles: FrpProfileSummary[] = [],
  activeOrigin?: string,
): string {
  const base = actionsPublicBaseUrl(profile, frpProfiles, activeOrigin);
  return base ? `${base.replace(/\/$/, "")}/privacy` : "";
}

export function actionsOAuthAuthorizeUrl(
  profile: WorkspaceProfile,
  frpProfiles: FrpProfileSummary[] = [],
  activeOrigin?: string,
): string {
  const base = actionsPublicBaseUrl(profile, frpProfiles, activeOrigin);
  return base ? `${base.replace(/\/$/, "")}/oauth/authorize` : "";
}

export function actionsOAuthTokenUrl(
  profile: WorkspaceProfile,
  frpProfiles: FrpProfileSummary[] = [],
  activeOrigin?: string,
): string {
  const base = actionsPublicBaseUrl(profile, frpProfiles, activeOrigin);
  return base ? `${base.replace(/\/$/, "")}/oauth/token` : "";
}
