/** Narrow display decision; do not infer a failure from a raw remote message. */
export interface RoutingDiagnostic {
  label: string;
  ok: boolean;
  skipped?: boolean;
  code?: string;
}

export function needsOAuthRoutingHelp(items: readonly RoutingDiagnostic[]): boolean {
  return items.some((item) => !item.ok && !item.skipped
    && item.label.startsWith("公网 MCP OAuth")
    && (item.code === "nginx_discovery_route_not_found"
      || item.code === "discovery_route_not_found"));
}

export const OAUTH_PROXY_PATHS = [
  "/.well-known/oauth-authorization-server",
  "/.well-known/oauth-protected-resource/mcp",
  "/.well-known/oauth-protected-resource",
  "/oauth/authorize",
  "/oauth/token",
] as const;
