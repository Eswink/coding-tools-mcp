<script lang="ts">
  import type { Snippet } from "svelte";
  let { title, description = "", children, icon, actions }:
    { title: string; description?: string; children: Snippet; icon?: Snippet; actions?: Snippet } = $props();
</script>
<section class="tx-card surface-card" aria-label={title}>
  <header><div class="card-identity">
    {#if icon}<span class="card-icon" aria-hidden="true">{@render icon()}</span>{/if}
    <div><h3>{title}</h3>{#if description}<p>{description}</p>{/if}</div>
  </div>{@render actions?.()}</header>
  {@render children()}
</section>
<style>
  .surface-card { padding:20px; }
  header { display:flex; align-items:center; justify-content:space-between; gap:16px; margin-bottom:18px; flex-wrap:wrap; }
  .card-identity { display:flex; align-items:center; gap:14px; min-width:0; }
  .card-icon { display:grid; place-items:center; width:46px; height:46px; flex-shrink:0; border-radius:12px; color:var(--primary); background:var(--primary-soft); }
  h3 { font-size:16px; font-weight:650; margin:0; }
  p { margin:4px 0 0; color:var(--text-secondary); font-size:13px; line-height:1.6; }
</style>
