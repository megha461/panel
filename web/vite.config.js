import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5193,
    // Engine on 8040. Taken already: 8000 visionvault, 8001 healthos, 8010
    // ad-resizer, 8020 ad-engine, 8030 evalrag; 5173 is healthos-web.
    proxy: { '/api': { target: 'http://127.0.0.1:8040', changeOrigin: true } },
  },
})
