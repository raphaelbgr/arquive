import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:64531',
        changeOrigin: true,
      },
      '/thumb': 'http://localhost:64531',
      '/vthumb': 'http://localhost:64531',
      '/file': 'http://localhost:64531',
      '/sprites': 'http://localhost:64531',
    },
  },
})
