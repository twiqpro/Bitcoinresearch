import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Always load btc-dashboard/.env even if the shell cwd is the monorepo root.
const HERE = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  root: HERE,
  envDir: HERE,
  plugins: [react()],
  server: {
    port: 5173,
  },
});
