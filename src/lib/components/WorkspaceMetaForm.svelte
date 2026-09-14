<script lang="ts">
  import { onDestroy } from "svelte";
  import { selectedDirectory } from "$lib/runtime/configuration";
  import { FolderInput, FolderOpen } from "@lucide/svelte";
  import { open } from "@tauri-apps/plugin-dialog";
  import { openWorkspaceDirectory } from "$lib/api/workspaces";
  import { showToast } from "$lib/stores/toast";

  interface Props {
    workspaceId: string;
    name: string;
    path: string;
    onSave: (name: string) => void | Promise<void>;
    onUpdatePath: (path: string) => void | Promise<void>;
  }

  let { workspaceId, name, path, onSave, onUpdatePath }: Props = $props();

  let disposed = false;
  onDestroy(() => { disposed = true; });

  let draftName = $state("");
  let saving = $state(false);
  let opening = $state(false);
  let updatingPath = $state(false);

  const dirty = $derived(draftName.trim() !== name && draftName.trim().length > 0);

  $effect(() => {
    draftName = name;
  });

  async function save() {
    if (saving || !dirty) return;
    saving = true;
    try {
      await onSave(draftName.trim());
    } catch (error) {
      if (!disposed) showToast(String(error), { title: "名称保存失败", kind: "error" });
    } finally {
      saving = false;
    }
  }

  async function openDirectory() {
    if (opening || !path.trim()) return;
    opening = true;
    try {
      await openWorkspaceDirectory(path);
    } catch (error) {
      showToast(String(error), {
        kind: "error",
        title: "无法打开目录",
      });
    } finally {
      opening = false;
    }
  }

  async function updateDirectory() {
    if (updatingPath) return;
    updatingPath = true;
    const id = workspaceId;
    const previousPath = path;
    const apply = onUpdatePath;
    try {
      const selected = await open({
        directory: true,
        multiple: false,
        defaultPath: previousPath.trim() || undefined,
      });
      if (!selected || Array.isArray(selected) || disposed || id !== workspaceId) return;
      const nextPath = selectedDirectory(selected);
      if (!nextPath || nextPath === selectedDirectory(previousPath)) return;
      await apply(nextPath);
    } catch (error) {
      showToast(String(error), {
        kind: "error",
        title: "无法更新目录",
      });
    } finally {
      updatingPath = false;
    }
  }
</script>

<form
  class="tx-card workspace-meta"
  onsubmit={(event) => {
    event.preventDefault();
    void save();
  }}
>
  <label class="tx-field meta-name">
    <span class="tx-label">工作区名称</span>
    <input type="text" class="tx-input" bind:value={draftName} />
  </label>
  <div class="tx-field meta-path">
    <span class="tx-label">路径</span>
    <div class="path-controls">
      <p
        class="tx-mono min-w-0 flex-1 truncate rounded-[10px] border border-[var(--border)] bg-[var(--field-bg)] px-2.5 py-2 text-[var(--color-text-secondary)]"
        title={path}
      >
        {path}
      </p>
      <button
        type="button"
        class="tx-btn-ghost"
        disabled={opening || !path.trim()}
        onclick={() => void openDirectory()}
      >
        <FolderOpen size={14} class="inline-block" />
        <span class="ml-1">{opening ? "打开中…" : "打开目录"}</span>
      </button>
      <button
        type="button"
        class="tx-btn-ghost"
        disabled={updatingPath}
        onclick={() => void updateDirectory()}
      >
        <FolderInput size={14} class="inline-block" />
        <span class="ml-1">{updatingPath ? "选择中…" : "更新目录"}</span>
      </button>
    </div>
  </div>
  <button type="submit" class="tx-btn-primary shrink-0" disabled={saving || !dirty}>
    {saving ? "保存中…" : "保存名称"}
  </button>
</form>

<style>
  .workspace-meta { display:grid; grid-template-columns:minmax(160px,.8fr) minmax(0,1.8fr) auto; gap:18px; padding:18px; align-items:end; }
  .meta-name,.meta-path { min-width:0; }
  .path-controls { display:flex; align-items:center; gap:10px; min-width:0; }
  .path-controls p { min-height:42px; display:flex; align-items:center; }
  @media(max-width:1200px) { .workspace-meta { grid-template-columns:minmax(0,1fr) auto; } .meta-name { grid-column:1; } .meta-path { grid-column:1/-1; grid-row:2; } }
</style>
