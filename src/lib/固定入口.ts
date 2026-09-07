/** Preview/validation only; the Rust resolver remains authoritative at runtime. */
export interface FrpRouteOptions {
  domain_mode: "subdomain" | "custom";
  custom_domain: string;
  subdomain_host: string;
  public_port: number;
  proxy_type: "http" | "https";
  local_ip: string;
  local_port: number | null;
  https_mode: "https2http" | "local_tls";
  tls_cert_file: string;
  tls_key_file: string;
  use_compression: boolean;
  tcp_mux: boolean;
  tls_enable: boolean;
}

export function defaultFrpOptions(input?: Partial<FrpRouteOptions>): FrpRouteOptions {
  return {
    domain_mode: "subdomain", custom_domain: "", subdomain_host: "",
    public_port: 443, proxy_type: "http", local_ip: "127.0.0.1", local_port: null,
    https_mode: "https2http", tls_cert_file: "", tls_key_file: "",
    use_compression: false, tcp_mux: true, tls_enable: true,
    ...input,
  };
}

export function strictPort(value: number | string | null | undefined): number {
  const port = typeof value === "number" ? value : Number(value);
  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    throw new Error("端口必须为 1–65535 的整数。");
  }
  return port;
}

function validLabel(value: string): boolean {
  return value.length >= 1 && value.length <= 63
    && /^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$/i.test(value);
}

export function normalizeDomain(value: string): string {
  const domain = value.trim().replace(/\.+$/, "").toLowerCase();
  const parts = domain.split(".");
  if (domain.length > 253 || parts.length < 2 || !parts.every(validLabel)
      || /^\d+$/.test(parts[parts.length - 1])) {
    throw new Error("请填写完整域名，不要包含协议、端口、路径、通配符或 IP。");
  }
  return domain;
}

export function normalizeServerHost(value: string): string {
  const host = value.trim().replace(/^\[(.*)\]$/, "$1");
  if (host.includes(":")) {
    try {
      const url = new URL(`http://[${host}]`);
      return url.hostname.slice(1, -1);
    } catch {
      throw new Error("地址只接受 IP 或主机名；控制端口需要单独填写。");
    }
  }
  const normalized = host.replace(/\.+$/, "").toLowerCase();
  if (!normalized || normalized.length > 253 || !normalized.split(".").every(validLabel)) {
    throw new Error("地址只接受 IP 或主机名，不要包含协议、路径或端口。");
  }
  return normalized;
}

export function normalizePublicOrigin(value: string): string {
  const text = value.trim();
  const message = "公网地址必须是 HTTPS 根地址，不要附带 /mcp、凭据、查询或片段。";
  if (!text || /[\s\x00-\x1f\x7f\\?#]/.test(text)) throw new Error(message);
  const parts = text.split("://");
  if (parts.length !== 2) throw new Error(message);
  const rest = parts[1];
  const slash = rest.indexOf("/");
  const authority = slash < 0 ? rest : rest.slice(0, slash);
  if (!authority || authority.includes("@") || (slash >= 0 && slash !== rest.length - 1)) {
    throw new Error(message);
  }
  let url: URL;
  try { url = new URL(text); } catch { throw new Error(message); }
  if (url.protocol !== "https:" || !url.hostname || url.username || url.password || url.port === "0") {
    throw new Error(message);
  }
  return url.origin;
}

export function isQuickTunnelOrigin(value: string): boolean {
  try {
    const host = new URL(value).hostname.toLowerCase().replace(/\.+$/, "");
    return host === "trycloudflare.com" || host.endsWith(".trycloudflare.com");
  } catch { return false; }
}

export function normalizeNamedOrigin(value: string): string {
  const origin = normalizePublicOrigin(value);
  if (isQuickTunnelOrigin(origin)) throw new Error("Named Tunnel 需要自有固定域名，不能使用 trycloudflare.com。");
  const url = new URL(origin);
  url.hostname = normalizeDomain(url.hostname);
  return url.origin;
}

export function frpOrigin(server: string, subdomain: string, input?: Partial<FrpRouteOptions>): string {
  const options = defaultFrpOptions(input);
  let host: string;
  if (options.domain_mode === "custom") {
    host = normalizeDomain(options.custom_domain);
  } else if (options.domain_mode === "subdomain") {
    const prefix = subdomain.trim().toLowerCase();
    if (!validLabel(prefix)) throw new Error("子域名前缀无效。");
    let suffix: string;
    try { suffix = normalizeDomain(options.subdomain_host.trim() || server); }
    catch { throw new Error("服务器 IP 不能作为域名后缀：请填写独立后缀或选择完整自定义域名。"); }
    host = normalizeDomain(`${prefix}.${suffix}`);
  } else {
    throw new Error("未知 FRP 域名模式。");
  }
  const port = strictPort(options.public_port);
  return `https://${host}${port === 443 ? "" : `:${port}`}`;
}

export function validateFrpOptions(server: string, subdomain: string, input: Partial<FrpRouteOptions>, servicePort: number): FrpRouteOptions {
  normalizeServerHost(server);
  const options = defaultFrpOptions(input);
  frpOrigin(server, subdomain, options);
  options.public_port = strictPort(options.public_port);
  options.local_ip = normalizeServerHost(options.local_ip);
  options.local_port = options.local_port == null ? null : strictPort(options.local_port);
  const targetPort = options.local_port ?? strictPort(servicePort);
  if (options.domain_mode === "custom") options.custom_domain = normalizeDomain(options.custom_domain);
  if (options.domain_mode === "subdomain" && options.subdomain_host.trim()) options.subdomain_host = normalizeDomain(options.subdomain_host);
  if (options.proxy_type === "https") {
    if (options.https_mode === "https2http") {
      if (!options.tls_cert_file.trim() || !options.tls_key_file.trim()
          || options.tls_cert_file.includes("\0") || options.tls_key_file.includes("\0")) {
        throw new Error("https2http 需要填写有效的证书和私钥文件路径。");
      }
    } else if (options.https_mode === "local_tls") {
      if (options.local_port == null) throw new Error("HTTPS 透传必须显式填写已有 HTTPS 服务端口。");
      const local = options.local_ip.toLowerCase();
      if (targetPort === servicePort && (local === "localhost" || local === "::1" || local === "::"
          || local === "0.0.0.0" || /^127\./.test(local))) {
        throw new Error("内置 MCP/Actions 端口是普通 HTTP，不能直接作为 HTTPS 透传目标。");
      }
    } else throw new Error("未知 HTTPS 转发模式。");
  } else if (options.proxy_type !== "http") throw new Error("不支持的 FRP 代理类型。");
  return options;
}

function tomlString(value: string): string {
  return JSON.stringify(value).replace(/\x7f/g, "\\u007F");
}

/** Always redacted. Never execute this frontend preview as a configuration. */
export function frpConfigPreview(server: string, serverPort: number, subdomain: string, options: FrpRouteOptions, servicePort: number): string {
  const host = normalizeServerHost(server);
  const normalized = validateFrpOptions(host, subdomain, options, servicePort);
  const lines = [
    `serverAddr = ${tomlString(host)}`, `serverPort = ${strictPort(serverPort)}`,
    'auth.method = "token"', 'auth.token = "<REDACTED>"',
    `transport.tcpMux = ${normalized.tcp_mux}`, `transport.tls.enable = ${normalized.tls_enable}`,
    "loginFailExit = false", "transport.heartbeatInterval = 30", "transport.heartbeatTimeout = 90", "",
    "[[proxies]]", 'name = "workspace-preview"', `type = ${tomlString(normalized.proxy_type)}`,
    `transport.useCompression = ${normalized.use_compression}`,
  ];
  if (normalized.domain_mode === "custom") lines.push(`customDomains = [${tomlString(normalized.custom_domain)}]`);
  else lines.push(`subdomain = ${tomlString(subdomain.trim().toLowerCase())}`);
  const port = normalized.local_port ?? servicePort;
  if (normalized.proxy_type === "https" && normalized.https_mode === "https2http") {
    const target = normalized.local_ip.includes(":") ? `[${normalized.local_ip}]:${port}` : `${normalized.local_ip}:${port}`;
    lines.push('plugin.type = "https2http"', `plugin.localAddr = ${tomlString(target)}`,
      `plugin.crtPath = ${tomlString(normalized.tls_cert_file.trim())}`, `plugin.keyPath = ${tomlString(normalized.tls_key_file.trim())}`);
  } else {
    lines.push(`localIP = ${tomlString(normalized.local_ip)}`, `localPort = ${port}`);
  }
  return lines.join("\n");
}
