import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { '@': path.resolve(__dirname, './src') } },
  server: {
    port: 5173,
    proxy: { '/api': process.env.METRICAIRN_API_URL || 'http://localhost:8000', '/health': process.env.METRICAIRN_API_URL || 'http://localhost:8000', '/static': process.env.METRICAIRN_API_URL || 'http://localhost:8000' },
  },
})
