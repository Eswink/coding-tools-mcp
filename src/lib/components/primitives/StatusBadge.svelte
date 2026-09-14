<script lang="ts">
  import type { RuntimeState } from "$lib/types";
  let { state }: { state: RuntimeState } = $props();
  const labels: Record<RuntimeState, string> = { running: "运行中", starting: "启动中", stopping: "停止中", stopped: "已停止", error: "错误" };
</script>
<span class="status-badge" class:healthy={state === "running"} class:failed={state === "error"} class:pending={state === "starting" || state === "stopping"}>
  <span class="dot" aria-hidden="true"></span>{labels[state]}
</span>
<style>
  .status-badge { display:inline-flex; gap:7px; align-items:center; padding:5px 12px; border-radius:999px; font-size:12px; font-weight:600; background:var(--field-bg); color:var(--text-secondary); white-space:nowrap; }
  .healthy { color:var(--success); background:var(--success-soft); }
  .failed { color:var(--danger); background:var(--surface-hover); }
  .pending { color:var(--warning); background:var(--warning-soft); }
  .dot { width:8px; height:8px; border-radius:50%; background:currentColor; }
</style>
