<script lang="ts">
  import { OAUTH_PROXY_PATHS } from "$lib/runtime/oauth-routing";
</script>

<details class="mt-3 rounded-lg border border-[var(--color-border)] p-3 text-sm">
  <summary class="cursor-pointer font-medium">修复公网 OAuth 路由（Nginx / FRP / Cloudflare）</summary>
  <p class="mt-2 text-[var(--color-text-muted)]">
    /mcp 可达不代表 OAuth 发现可用。下列路径必须保留原始 URI，转发到与现有 /mcp 相同的 MCP 上游：
  </p>
  <ul class="mt-2 space-y-1">
    {#each OAUTH_PROXY_PATHS as path}
      <li><code class="break-all text-xs">{path}</code></li>
    {/each}
  </ul>
  <p class="mt-2 text-[var(--color-text-muted)]">
    Nginx：检查 /.well-known/ 静态目录、证书验证及隐藏路径规则；优先给这三个发现端点配置精确 location，保留 ACME 与隐藏文件保护。proxy_pass 不应额外附加 URI。
  </p>
  <p class="mt-2 text-[var(--color-text-muted)]">
    上游必须复用该站点已工作的 /mcp 目标及 Host 设置。网关与桌面不在同一主机时，网关的 127.0.0.1 不是桌面地址。FRP 核对域名路由；Cloudflare Named 核对远程配置，不能只匹配 /mcp。
  </p>
  <p class="mt-2 text-[var(--color-text-muted)]">
    先备份并检查配置语法，再重载并重新运行公网检查。不要关闭 OAuth、公开密钥或把错误页伪装为 JSON。仓库 docs/deployment/public-oauth-routing.md 提供模板、验收与回滚步骤。
  </p>
</details>
