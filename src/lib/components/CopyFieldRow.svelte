<script lang="ts">
  import CopyButton from "$lib/components/CopyButton.svelte";

  interface Props {
    label: string;
    value: string;
    hint?: string;
    loading?: boolean;
    secret?: boolean;
  }

  let { label, value, hint = "", loading = false, secret = false }: Props = $props();

  let visible = $state(false);
  $effect(() => { value; label; loading; secret; visible = false; });
  const display = $derived(loading ? "加载中…" : !value ? "未配置"
    : secret && !visible ? "••••••••••••" : value);
  const canCopy = $derived(!loading && value.length > 0);
</script>

<div class="tx-info-block">
  <div class="tx-info-row">
    <span class="tx-info-label">{label}</span>
    {#if canCopy}
      <div class="flex items-center gap-2">
        {#if secret}
          <button type="button" class="tx-btn-ghost text-xs" aria-pressed={visible}
            onclick={() => { visible = !visible; }}>{visible ? "隐藏" : "显示"}</button>
        {/if}
        <CopyButton {value} />
      </div>
    {/if}
  </div>
  <p class="tx-mono mt-1.5 truncate text-sm text-[var(--color-text-secondary)]">{display}</p>
  {#if hint}
    <p class="mt-1 text-[11px] text-[var(--color-text-muted)]">{hint}</p>
  {/if}
</div>
