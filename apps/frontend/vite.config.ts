import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In dev, proxy /api to the FastAPI backend so there are no CORS hops.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": "http://localhost:8000" },
  },
});
