import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In development, /api/* is forwarded to the FastAPI server on port 8000.
// In Docker, nginx does the same forwarding (see nginx.conf).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
