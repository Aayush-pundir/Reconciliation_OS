import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    // Deliberately not 5173 (Vite's default) - avoids colliding with other
    // projects' dev servers running locally at the same time.
    port: 7401,
    proxy: {
      "/api": {
        target: "http://localhost:7400",
        changeOrigin: true,
      },
    },
  },
});
