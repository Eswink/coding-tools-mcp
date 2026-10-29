import { defineConfig } from "vite";
import { sveltekit } from "@sveltejs/kit/vite";
import { vitePreprocess } from "@sveltejs/vite-plugin-svelte";
import adapter from "@sveltejs/adapter-static";
import tailwindcss from "@tailwindcss/vite";

// @ts-expect-error process is a nodejs global
const host = process.env.TAURI_DEV_HOST;

// SvelteKit 3: config moves into sveltekit(...) in vite.config.js
// (svelte.config.js is no longer supported). SPA fallback retained for Tauri.
export default defineConfig(async () => ({
  plugins: [
    tailwindcss(),
    sveltekit({
      preprocess: vitePreprocess(),
      adapter: adapter({
        fallback: "index.html",
      }),
      // Kit3: files.lib removed; keep $lib for existing imports via deprecated alias
      // (prefer subpath imports long-term; not in scope for audit tip).
      alias: {
        $lib: "src/lib",
      },
    }),
  ],
  clearScreen: false,
  server: {
    port: 1420,
    strictPort: true,
    host: host || false,
    hmr: host
      ? {
          protocol: "ws",
          host,
          port: 1421,
        }
      : undefined,
    watch: {
      ignored: ["**/src-tauri/**"],
    },
  },
}));
