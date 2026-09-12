<script lang="ts">
  import { onDestroy } from "svelte";
  import { secretIsSet } from "$lib/api/secrets";
  import type { TunnelSecretUpdate } from "$lib/api/workspaces";
  import SecretInput from "$lib/components/SecretInput.svelte";

  interface Props {
    workspaceId: string;
    secretKey: TunnelSecretUpdate["key"];
    label?: string;
    hasPending?: boolean;
  }
  let { workspaceId, secretKey, label = "Cloudflare Tunnel Token", hasPending = $bindable(false) }: Props = $props();
  let draft = $state("");
  let saved = $state(false);
  let loading = $state(true);
  let error = $state("");
  let loadSeq = 0;
  let disposed = false;
  onDestroy(() => { disposed = true; loadSeq++; draft = ""; });
  const placeholder = $derived(saved && !draft ? "已保存（点击更新）" : "粘贴 Tunnel Token");
  $effect(() => { hasPending = draft.trim().length > 0; });
  $effect(() => {
    const id = workspaceId, key = secretKey;
    void load(id, key);
    return () => { loadSeq++; };
  });
  async function load(id: string, key: TunnelSecretUpdate["key"]) {
    const seq = ++loadSeq;
    draft = ""; saved = false; error = ""; loading = true;
    try {
      const exists = await secretIsSet(id, key);
      if (!disposed && seq === loadSeq && id === workspaceId && key === secretKey) saved = exists;
    } catch {
      if (!disposed && seq === loadSeq) error = "凭据状态读取失败，请重新打开配置后重试。";
    } finally { if (!disposed && seq === loadSeq) loading = false; }
  }
  export function pendingUpdate(): TunnelSecretUpdate | undefined {
    if (disposed || loading || error) throw new Error("凭据状态尚未确认，无法保存。");
    const value = draft.trim();
    return value ? { key: secretKey, value } : undefined;
  }
  export async function refreshSaved() { if (!disposed) await load(workspaceId, secretKey); }
</script>

<label class="grid gap-1">
  <span class="text-xs text-[var(--color-text-muted)]">{label}</span>
  <SecretInput bind:value={draft} {placeholder} disabled={loading || !!error} showCopy={false} />
  {#if error}<span role="alert" class="text-xs text-red-600">{error}</span>{/if}
</label>
