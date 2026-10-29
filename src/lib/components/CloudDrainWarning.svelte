<script lang="ts">
  import { onMount } from 'svelte';
  import { listen } from '@tauri-apps/api/event';
  import { watchCloudDrain } from '$lib/cloud-drain-warning';
  import { showToast } from '$lib/stores/toast';
  onMount(() => watchCloudDrain(listen, message => {
    showToast(message, { title: '云连接需要本机核查', kind: 'warning', duration: 0 });
  }));
</script>
