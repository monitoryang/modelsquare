import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // Proxy SRS HTTP-FLV stream for development
      '/live': {
        target: 'http://localhost:8090',
        changeOrigin: true,
      },
      // Proxy API requests for development
      '/api': {
        target: 'http://localhost:8020',
        changeOrigin: true,
      },
    },
  },
})
