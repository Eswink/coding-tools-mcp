<script lang="ts">
  import { ChevronRight } from "@lucide/svelte";
  import type { Snippet } from "svelte";
  let { title, description = "", section = "全局设置", icon, status, actions }:
    { title: string; description?: string; section?: string; icon?: Snippet; status?: Snippet; actions?: Snippet } = $props();
</script>
<header class="page-heading">
  <nav class="breadcrumb" aria-label="面包屑">
    <a href="/">工作区</a><ChevronRight size={15} aria-hidden="true" />
    {#if section !== "工作区"}<span>{section}</span><ChevronRight size={15} aria-hidden="true" />{/if}
    <span class="current-crumb" aria-current="page" title={title}>{title}</span>
  </nav>
  <div class="title-row">
    <div class="identity">
      {#if icon}<span class="page-icon" aria-hidden="true">{@render icon()}</span>{/if}
      <div class="title-copy"><div class="title-status"><h2 class="page-title" title={title}>{title}</h2>{@render status?.()}</div>
        {#if description}<p>{description}</p>{/if}
      </div>
    </div>
    {#if actions}<div class="page-actions">{@render actions()}</div>{/if}
  </div>
</header>
<style>
  .page-heading { margin-bottom: 20px; }
  .breadcrumb { display:flex; align-items:center; flex-wrap:wrap; gap:9px; color:var(--text-secondary); font-size:13px; margin-bottom:20px; }
  .current-crumb { min-width:0; max-width:100%; overflow:hidden; white-space:nowrap; text-overflow:ellipsis; }
  .breadcrumb a:hover { color:var(--primary); text-decoration:underline; }
  .title-row { display:flex; justify-content:space-between; align-items:center; gap:20px; }
  .identity { display:flex; align-items:center; gap:16px; min-width:0; }
  .page-icon { width:56px; height:56px; display:grid; place-items:center; border-radius:16px; color:var(--primary); background:var(--primary-soft); flex-shrink:0; }
  .title-copy { min-width:0; }
  .title-status { display:flex; align-items:center; flex-wrap:wrap; gap:14px; }
  h2 { margin:0; min-width:0; max-width:100%; overflow-wrap:anywhere; display:-webkit-box; line-clamp:2; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }
  p { color:var(--text-secondary); margin:4px 0 0; font-size:14px; line-height:1.6; }
  .page-actions { display:flex; gap:10px; flex-shrink:0; }
  @media (max-width:1100px) { .title-row { align-items:flex-start; flex-wrap:wrap; } .page-icon { width:48px; height:48px; } }
</style>
