<script lang="ts">
  import { Network, Zap } from "@lucide/svelte";
  import StatusBadge from "$lib/components/primitives/StatusBadge.svelte";
  import type { RuntimeState } from "$lib/types";
  let { value, mcpState, actionsState, disabled = false, onchange }:
    { value: "mcp" | "actions"; mcpState: RuntimeState; actionsState: RuntimeState; disabled?: boolean; onchange: (value: "mcp" | "actions") => void } = $props();
</script>
<div class="service-switcher" role="group" aria-label="选择服务">
  <button type="button" class="service-choice" class:active={value === "mcp"} aria-pressed={value === "mcp"} {disabled} onclick={() => onchange("mcp")}>
    <Network size={19} aria-hidden="true" /><span>MCP 服务</span><StatusBadge state={mcpState} />
  </button>
  <button type="button" class="service-choice" class:active={value === "actions"} aria-pressed={value === "actions"} {disabled} onclick={() => onchange("actions")}>
    <Zap size={19} aria-hidden="true" /><span>Actions 服务</span><StatusBadge state={actionsState} />
  </button>
</div>
<style>
  .service-switcher { display:flex; flex-wrap:wrap; gap:12px; margin-top:20px; }
  .service-choice { display:flex; align-items:center; gap:10px; padding:7px 16px; min-height:46px; border:1px solid var(--border); border-radius:999px; background:var(--card-bg); color:var(--text-main); cursor:pointer; font-size:14px; font-weight:600; }
  .service-choice:hover:not(:disabled) { border-color:var(--primary); }
  .active { border-color:var(--primary); background:var(--primary-soft); color:var(--primary); }
</style>
