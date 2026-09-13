<script lang="ts">
  import { Moon, Sun } from "@lucide/svelte";
  import { onMount } from "svelte";
  import { initializeTheme, effectiveTheme, toggleTheme } from "$lib/stores/theme";
  onMount(initializeTheme);
</script>
<button type="button" class="theme-toggle" onclick={toggleTheme} aria-label="切换主题" title={$effectiveTheme === "dark" ? "切换为浅色" : "切换为深色"}>
  {#if $effectiveTheme === "dark"}<Sun size={19} aria-hidden="true" />{:else}<Moon size={19} aria-hidden="true" />{/if}
</button>
<style>
  .theme-toggle { display:grid; place-items:center; width:42px; height:42px; flex-shrink:0; border-radius:12px; border:1px solid #44587c; background:#213958; color:#d6e5ff; cursor:pointer; }
  .theme-toggle:hover { background:#304a70; }
</style>
