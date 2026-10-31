import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In dev, /api/* is forwarded to the FastAPI app (uvicorn on :8000), so the browser talks
// to one origin and the API needs no CORS settings. docker-compose does the same with nginx.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": {
        target: process.env.API_URL ?? "http://localhost:8000",
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
