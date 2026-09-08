<script lang="ts">
  import { onMount } from "svelte";
  import { listFrpProfiles, type FrpProfileDto } from "$lib/api/settings";
  import { testTunnel as invokeTunnelTest } from "$lib/api/tunnel";
  import SecretTokenField from "$lib/components/SecretTokenField.svelte";
  import { showToast } from "$lib/stores/toast";
  import {
    defaultFrpOptions, frpConfigPreview, frpOrigin, isQuickTunnelOrigin,
    normalizeNamedOrigin, normalizePublicOrigin, normalizeServerHost,
    strictPort, validateFrpOptions, type FrpRouteOptions,
  } from "$lib/固定入口";

  export interface TunnelFormConfig {
    type: string;
    public_url: string;
    frp_server: string;
    frp_subdomain: string;
    frp_profile_id: string;
    frp_server_port: number;
    frp: FrpRouteOptions;
    cloudflare_mode: string;
    cloudflare_http2: boolean;
    use_proxy: boolean;
  }

  export interface SaveTunnelOptions {
    skipTunnelRestart?: boolean;
    skipServicePrompt?: boolean;
  }

  interface Props {
    workspaceId: string;
    service: "mcp" | "actions";
    localPort?: number;
    activePublicOrigin?: string;
    onTested?: () => void | Promise<void>;
    config: TunnelFormConfig;
    onSave: (config: TunnelFormConfig, options?: SaveTunnelOptions) => void | Promise<void>;
  }

  let { workspaceId, service, localPort = 28766, activePublicOrigin = "", onTested, config, onSave }: Props = $props();
  let draft = $state<TunnelFormConfig>({
    type: "none", public_url: "", frp_server: "", frp_subdomain: "",
    frp_profile_id: "", frp_server_port: 7000, frp: defaultFrpOptions(),
    cloudflare_mode: "quick", cloudflare_http2: true, use_proxy: true,
  });
  let saving = $state(false);
  let testing = $state(false);
  let tokenField = $state<SecretTokenField | null>(null);
  let tokenPending = $state(false);
  let frpProfiles = $state<FrpProfileDto[]>([]);

  const showFrp = $derived(draft.type === "frp");
  const showCloudflare = $derived(draft.type === "cloudflare");
  const isNamed = $derived(showCloudflare && draft.cloudflare_mode === "named");
  const isQuick = $derived(showCloudflare && draft.cloudflare_mode === "quick");
  const selectedProfile = $derived(frpProfiles.find((item) => item.id === draft.frp_profile_id));
  const useGlobalProfile = $derived(Boolean(draft.frp_profile_id));
  const server = $derived(useGlobalProfile ? selectedProfile?.server ?? "" : draft.frp_server);
  const serverPort = $derived(useGlobalProfile ? selectedProfile?.serverPort ?? 7000 : draft.frp_server_port);
  const canTest = $derived(showFrp || showCloudflare);
  const showToken = $derived(isNamed || (showFrp && !useGlobalProfile));
  const secretKey = $derived(
    service === "mcp"
      ? showFrp ? ("frp_token" as const) : ("cloudflare_token" as const)
      : showFrp ? ("actions_frp_token" as const) : ("actions_cloudflare_token" as const),
  );
  const dirty = $derived(JSON.stringify(draft) !== JSON.stringify({
    ...config, frp: defaultFrpOptions(config.frp),
    frp_profile_id: config.frp_profile_id ?? "",
    cloudflare_http2: config.cloudflare_http2 ?? true,
    use_proxy: config.use_proxy ?? true,
  }) || tokenPending);

  const preview = $derived.by(() => {
    if (!showFrp) return { origin: "", text: "", error: "" };
    try {
      return {
        origin: frpOrigin(server, draft.frp_subdomain, draft.frp),
        text: frpConfigPreview(server, serverPort, draft.frp_subdomain, draft.frp, localPort),
        error: "",
      };
    } catch (error) {
      return { origin: "", text: "", error: String(error).replace(/^Error: /, "") };
    }
  });

  $effect(() => {
    // Copy the nested route: editing the form must not mutate the saved profile.
    draft = {
      ...config, frp: defaultFrpOptions(config.frp),
      frp_profile_id: config.frp_profile_id ?? "",
      cloudflare_http2: config.cloudflare_http2 ?? true,
      use_proxy: config.use_proxy ?? true,
    };
  });

  onMount(async () => {
    try { frpProfiles = await listFrpProfiles(); }
    catch (error) { showToast(String(error), { title: "FRP 配置读取失败", kind: "error" }); }
  });

  function changeProvider(value: string) {
    if (draft.type === value) return;
    draft.type = value;
    draft.public_url = "";
  }

  function changeCloudflareMode(value: string) {
    draft.cloudflare_mode = value;
    if (value === "quick" || isQuickTunnelOrigin(draft.public_url)) draft.public_url = "";
  }

  function validatedDraft(): TunnelFormConfig {
    const payload = { ...draft, frp: { ...draft.frp } };
    if (showFrp) {
      if (useGlobalProfile && !selectedProfile) throw new Error("所选 FRP 配置已不存在，请重新选择。");
      strictPort(serverPort);
      payload.frp.local_port = draft.frp.local_port === null ? null : strictPort(draft.frp.local_port);
      payload.frp = validateFrpOptions(server, draft.frp_subdomain, payload.frp, localPort);
      payload.frp_subdomain = draft.frp_subdomain.trim().toLowerCase();
      if (!useGlobalProfile) {
        payload.frp_server = normalizeServerHost(server);
        payload.frp_server_port = strictPort(serverPort);
      }
      payload.public_url = frpOrigin(server, payload.frp_subdomain, payload.frp);
    } else if (isNamed) {
      payload.public_url = normalizeNamedOrigin(draft.public_url);
    } else if (isQuick) {
      // A cached temporary address is informational, not a domain binding.
      payload.public_url = "";
    } else if (draft.type === "none") {
      payload.public_url = draft.public_url.trim() ? normalizePublicOrigin(draft.public_url) : "";
    } else {
      throw new Error("未知隧道类型或 Cloudflare 模式。");
    }
    return payload;
  }

  async function saveDraft(options?: SaveTunnelOptions) {
    const payload = validatedDraft();
    // Do not save a credential for a form which has already failed validation.
    if (tokenField && showToken) await tokenField.saveIfDirty();
    await onSave(payload, options);
  }

  async function save() {
    if (saving || testing || !dirty) return;
    saving = true;
    try {
      await saveDraft();
      showToast("隧道配置已保存；公网可用性请通过健康检查确认。", { title: "保存成功", kind: "success" });
    } catch (error) {
      showToast(String(error), { title: "保存失败", kind: "error", duration: 8000 });
    } finally { saving = false; }
  }

  async function testTunnelConnection() {
    if (!canTest || testing || saving) return;
    testing = true;
    try {
      validatedDraft();
      if (dirty) await saveDraft({ skipTunnelRestart: true, skipServicePrompt: true });
      const result = await invokeTunnelTest(workspaceId, service);
      await onTested?.();
      showToast(`${result.message}${result.publicUrl ? `\n${result.publicUrl}` : ""}`, {
        title: result.success ? "隧道测试完成" : "测试未完成",
        kind: result.success ? "success" : "warning", duration: 8000,
      });
    } catch (error) {
      showToast(String(error), { title: "测试失败", kind: "error", duration: 8000 });
    } finally { testing = false; }
  }
</script>

<form class="grid gap-3" onsubmit={(event) => { event.preventDefault(); void save(); }}>
  <fieldset class="grid min-w-0 gap-3" disabled={saving || testing}>
    <label class="grid gap-1">
      <span class="text-xs text-[var(--color-text-muted)]">隧道类型</span>
      <select class="tx-input" value={draft.type} onchange={(event) => changeProvider(event.currentTarget.value)}>
        <option value="none">未配置 / 外部反向代理</option>
        <option value="frp">FRP</option>
        <option value="cloudflare">Cloudflare</option>
      </select>
    </label>

    {#if canTest}
      <label class="flex items-center gap-2 text-xs">
        <input type="checkbox" bind:checked={draft.use_proxy} />
        使用「设置 → 通用」中的网络代理连接隧道
      </label>
    {/if}

    {#if showFrp}
      <label class="grid gap-1">
        <span class="text-xs text-[var(--color-text-muted)]">FRP 服务器配置</span>
        <select class="tx-input" bind:value={draft.frp_profile_id}>
          <option value="">手动填写服务器 IP / 主机名</option>
          {#each frpProfiles as item (item.id)}
            <option value={item.id}>{item.name} · {item.server}:{item.serverPort}</option>
          {/each}
        </select>
      </label>
      {#if useGlobalProfile}
        <p class="text-xs text-[var(--color-text-muted)]">
          {selectedProfile ? `${selectedProfile.server}:${selectedProfile.serverPort} · Token ${selectedProfile.hasToken ? "已配置" : "未配置"}` : "所选服务器配置不存在"}
        </p>
      {:else}
        <div class="grid gap-3 sm:grid-cols-2">
          <label class="grid gap-1"><span class="text-xs">服务器地址（IP / 主机名）</span>
            <input class="tx-input font-mono" placeholder="203.0.113.10" bind:value={draft.frp_server} />
          </label>
          <label class="grid gap-1"><span class="text-xs">FRPS 控制端口</span>
            <input class="tx-input" type="number" min="1" max="65535" step="1" bind:value={draft.frp_server_port} />
          </label>
        </div>
      {/if}

      <label class="grid gap-1"><span class="text-xs">域名模式</span>
        <select class="tx-input" bind:value={draft.frp.domain_mode}>
          <option value="custom">完整自定义域名（与服务器 IP 独立）</option>
          <option value="subdomain">传统子域名（兼容已有配置）</option>
        </select>
      </label>
      {#if draft.frp.domain_mode === "custom"}
        <label class="grid gap-1"><span class="text-xs">绑定的完整域名</span>
          <input class="tx-input font-mono" placeholder="mcp.example.com" bind:value={draft.frp.custom_domain} />
        </label>
      {:else}
        <div class="grid gap-3 sm:grid-cols-2">
          <label class="grid gap-1"><span class="text-xs">子域名前缀</span>
            <input class="tx-input font-mono" placeholder="my-mcp" bind:value={draft.frp_subdomain} />
          </label>
          <label class="grid gap-1"><span class="text-xs">独立域名后缀（FRPS subDomainHost）</span>
            <input class="tx-input font-mono" placeholder="example.com" bind:value={draft.frp.subdomain_host} />
          </label>
        </div>
        <p class="text-xs text-[var(--color-text-muted)]">仅为兼容旧配置，后缀留空时使用有效的服务器域名；服务器 IP 不会被用作后缀。</p>
      {/if}
      <p class="text-xs text-[var(--color-text-muted)]">填写域名不会自动创建 DNS 或证书。请先将域名解析到公网 HTTPS 入口，并在服务器配置对应路由。</p>

      <label class="grid gap-1"><span class="text-xs">代理 / HTTPS 处理方式</span>
        <select class="tx-input" bind:value={draft.frp.proxy_type}>
          <option value="http">HTTP 转发（服务器反向代理终止公网 HTTPS）</option>
          <option value="https">HTTPS 转发（本地 TLS 或 https2http 插件）</option>
        </select>
      </label>
      {#if draft.frp.proxy_type === "https"}
        <label class="grid gap-1"><span class="text-xs">HTTPS 模式</span>
          <select class="tx-input" bind:value={draft.frp.https_mode}>
            <option value="https2http">https2http：证书终止 TLS，转发到本地 HTTP</option>
            <option value="local_tls">透传到已有本地 HTTPS 服务</option>
          </select>
        </label>
        {#if draft.frp.https_mode === "https2http"}
          <label class="grid gap-1"><span class="text-xs">证书文件绝对路径（PEM）</span>
            <input class="tx-input font-mono" placeholder="C:\certs\fullchain.pem" bind:value={draft.frp.tls_cert_file} />
          </label>
          <label class="grid gap-1"><span class="text-xs">私钥文件绝对路径（PEM）</span>
            <input class="tx-input font-mono" placeholder="C:\certs\privkey.pem" bind:value={draft.frp.tls_key_file} />
          </label>
        {:else}
          <p class="text-xs text-[var(--color-text-muted)]">必须显式指定真实 HTTPS 服务的端口；内置 MCP / Actions 端口是 HTTP，不能直接透传 TLS。</p>
        {/if}
      {/if}

      <details class="rounded-md border border-[var(--color-border)] p-3">
        <summary class="cursor-pointer text-xs">高级配置：目标地址、端口、压缩与连接 TLS</summary>
        <div class="mt-3 grid gap-3">
          <label class="grid gap-1"><span class="text-xs">本地目标地址</span>
            <input class="tx-input font-mono" bind:value={draft.frp.local_ip} />
          </label>
          <label class="flex items-center gap-2 text-xs">
            <input type="checkbox" checked={draft.frp.local_port !== null}
              onchange={(event) => { draft.frp.local_port = event.currentTarget.checked ? localPort : null; }} />
            覆盖目标端口（未启用时跟随 {service.toUpperCase()} 端口 {localPort}）
          </label>
          {#if draft.frp.local_port !== null}
            <label class="grid gap-1"><span class="text-xs">目标端口</span>
              <input class="tx-input" type="number" min="1" max="65535" step="1" bind:value={draft.frp.local_port} />
            </label>
          {/if}
          <label class="grid gap-1"><span class="text-xs">公网 HTTPS 端口（通常为 443）</span>
            <input class="tx-input" type="number" min="1" max="65535" step="1" bind:value={draft.frp.public_port} />
          </label>
          <label class="flex items-center gap-2 text-xs"><input type="checkbox" bind:checked={draft.frp.use_compression} />代理数据压缩</label>
          <label class="flex items-center gap-2 text-xs"><input type="checkbox" bind:checked={draft.frp.tcp_mux} />TCP 多路复用（需与 FRPS 匹配）</label>
          <label class="flex items-center gap-2 text-xs"><input type="checkbox" bind:checked={draft.frp.tls_enable} />FRPC ↔ FRPS 连接 TLS</label>
          <p class="text-xs text-[var(--color-text-muted)]">连接 TLS 不等于公网 HTTPS。同一工作区的 MCP 与 Actions 共用 FRPC 时，连接 TLS 与多路复用选项必须一致。</p>
        </div>
      </details>
      <label class="grid gap-1"><span class="text-xs">解析后的公网根地址</span>
        <input class="tx-input font-mono" readonly value={preview.origin} placeholder="完成配置后显示" />
      </label>
      {#if preview.error}<p role="status" class="text-xs text-[var(--color-text-muted)]">{preview.error}</p>{/if}
      {#if preview.text}
        <details class="rounded-md border border-[var(--color-border)] p-3">
          <summary class="cursor-pointer text-xs">TOML 预览（Token 已脱敏；实际配置由 Rust 生成并验证）</summary>
          <pre class="mt-3 overflow-x-auto whitespace-pre text-xs">{preview.text}</pre>
        </details>
      {/if}
    {/if}

    {#if showCloudflare}
      <label class="grid gap-1"><span class="text-xs">Cloudflare 模式</span>
        <select class="tx-input" value={draft.cloudflare_mode} onchange={(event) => changeCloudflareMode(event.currentTarget.value)}>
          <option value="named">Named Tunnel · 固定域名（长期接入，推荐）</option>
          <option value="quick">Quick Tunnel · 临时域名（重启会变化）</option>
        </select>
      </label>
      {#if isNamed}
        <div class="rounded-md border border-[var(--color-border)] p-3 text-xs leading-relaxed">
          在 Cloudflare 创建命名隧道，将固定主机名映射到
          <code>http://127.0.0.1:{localPort}</code>，然后填写该隧道的 Tunnel Token（不是账户 API Token）。
          必须转发该主机名的全部路径，包括 <code>/mcp</code>、<code>/oauth/*</code> 和 <code>/.well-known/*</code>。
          此表单不会自动创建 Cloudflare 路由或 DNS；本地端口变更后也需要同步远端路由。
        </div>
        <label class="grid gap-1"><span class="text-xs">固定公网根地址（不要附带 /mcp）</span>
          <input class="tx-input font-mono" type="url" placeholder="https://mcp.example.com" bind:value={draft.public_url} />
        </label>
        <p class="text-xs text-[var(--color-text-muted)]">从临时域名迁移后可能需要一次重新配置 / 授权。正常重启不再换域名；凭据过期或撤销仍需重新授权。</p>
      {:else if isQuick}
        <p class="text-xs text-[var(--color-text-muted)]">临时测试模式不适合长期绑定 ChatGPT。缓存地址或启用 HTTP/2 不会固定域名。</p>
        <label class="grid gap-1"><span class="text-xs">当前运行时发现的临时地址（公网可用性仍需健康检查）</span>
          <input class="tx-input font-mono" readonly value={activePublicOrigin} placeholder="启动后自动生成" />
        </label>
      {/if}
      <label class="flex items-center gap-2 text-xs"><input type="checkbox" bind:checked={draft.cloudflare_http2} />优先使用 HTTP/2（关闭后由 cloudflared 自动选择传输协议）</label>
    {/if}

    {#if showToken}
      {#key secretKey}
        <SecretTokenField bind:this={tokenField} bind:hasPending={tokenPending}
          {workspaceId} {secretKey} label={isNamed ? "Cloudflare Tunnel Token" : "FRP Token（可选）"} />
      {/key}
    {/if}
    {#if draft.type === "none"}
      <label class="grid gap-1"><span class="text-xs">外部反向代理公网根地址（可选）</span>
        <input class="tx-input font-mono" type="url" placeholder="https://mcp.example.com" bind:value={draft.public_url} />
      </label>
    {/if}
  </fieldset>
  <div class="flex justify-end gap-2 pt-1">
    {#if canTest}<button type="button" class="tx-btn-ghost" disabled={saving || testing} onclick={() => void testTunnelConnection()}>{testing ? "测试中…" : "测试连接"}</button>{/if}
    <button type="submit" class="tx-btn-ghost" disabled={saving || testing || !dirty}>{saving ? "保存中…" : "保存配置"}</button>
  </div>
</form>
