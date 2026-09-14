<script lang="ts">
  import { onMount } from "svelte";
  import { Sun, Moon, Monitor, Palette } from "@lucide/svelte";
  import SurfaceCard from "$lib/components/primitives/SurfaceCard.svelte";
  import { initializeTheme, themePreference, setTheme } from "$lib/stores/theme";
  onMount(initializeTheme);
</script>
<SurfaceCard title="外观主题" description="选择应用的外观；当前设备保存并立即生效。">
  {#snippet icon()}<Palette size={25} />{/snippet}
  <div class="theme-options" role="group" aria-label="外观主题">
    <button type="button" aria-pressed={$themePreference === "light"} onclick={() => setTheme("light")}><Sun size={22} aria-hidden="true" />浅色</button>
    <button type="button" aria-pressed={$themePreference === "dark"} onclick={() => setTheme("dark")}><Moon size={22} aria-hidden="true" />深色</button>
    <button type="button" aria-pressed={$themePreference === "system"} onclick={() => setTheme("system")}><Monitor size={22} aria-hidden="true" />跟随系统</button>
  </div>
</SurfaceCard>
<style>
  .theme-options { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:10px; }
  button { display:flex; flex-direction:column; align-items:center; gap:8px; padding:14px 8px; border-radius:10px; border:1px solid var(--border); background:var(--field-bg); color:var(--text-main); cursor:pointer; font-size:13px; }
  button[aria-pressed="true"] { border-color:var(--primary); color:var(--primary); background:var(--primary-soft); box-shadow:inset 0 0 0 1px var(--primary); }
</style>
