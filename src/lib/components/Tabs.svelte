<script lang="ts">
  interface TabItem { value: string; label: string; }
  interface Props {
    items: TabItem[]; value: string; onchange: (value: string) => void;
    label?: string; idPrefix?: string; panelId?: string; disabled?: boolean;
  }
  let { items, value, onchange, label = "页面分区", idPrefix = "section-tab", panelId, disabled = false }: Props = $props();
  // Manual activation: arrow navigation never discards an unsaved panel.
  // Enter/Space use the same guarded click callback as a pointer interaction.
  function moveFocus(event: KeyboardEvent) {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    const button = event.currentTarget as HTMLButtonElement;
    const tabs = Array.from(button.parentElement?.querySelectorAll<HTMLButtonElement>('button[role="tab"]:not(:disabled)') ?? []);
    const current = tabs.indexOf(button);
    if (current < 0 || tabs.length === 0) return;
    event.preventDefault();
    const index = event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1
      : (current + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
    tabs[index].focus();
  }
</script>
<div class="tx-tabs" role="tablist" aria-label={label}>
  {#each items as item (item.value)}
    <button type="button" role="tab" id={`${idPrefix}-${item.value}`} aria-controls={panelId}
      aria-selected={value === item.value} tabindex={value === item.value ? 0 : -1} {disabled}
      class="tx-tab" class:active={value === item.value} onkeydown={moveFocus} onclick={() => onchange(item.value)}>
      {item.label}
    </button>
  {/each}
</div>
