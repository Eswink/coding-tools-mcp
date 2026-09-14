<script lang="ts">
  import { Box } from "@lucide/svelte";
  import ServiceStatusPair from "$lib/components/ServiceStatusPair.svelte";
  import type { RuntimeState, WorkspaceProfile } from "$lib/types";

  interface Props {
    workspace: WorkspaceProfile;
    active: boolean;
    mcpState: RuntimeState;
    actionsState: RuntimeState;
    onClick: () => void;
  }

  let { workspace, active, mcpState, actionsState, onClick }: Props = $props();
</script>

<div class="tx-nav-item" class:active>
  <button type="button" class="tx-nav-button" aria-current={active ? "page" : undefined} title={workspace.name} onclick={onClick}>
    <Box size={20} aria-hidden="true" />
    <ServiceStatusPair mcp={mcpState} actions={actionsState} />
    <span class="min-w-0 flex-1 truncate text-sm font-medium">{workspace.name}</span>
  </button>
</div>
