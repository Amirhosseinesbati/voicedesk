import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', 'VITE_')
  return {
    plugins: [react(), tailwindcss()],
    server: {
      watch: { ignored: ['**/.tmp/**', '**/test-results/**'] },
      proxy: {
        '/api': {
          target: process.env.VITE_API_PROXY_TARGET || env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8000',
          changeOrigin: true,
          ws: true,
        },
      },
    },
  }
})
