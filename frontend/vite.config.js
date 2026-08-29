import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react-swc'

const userServiceProxy = {
  target: 'http://localhost:8001',
  changeOrigin: true,
}

const todoServiceProxy = {
  target: 'http://localhost:8002',
  changeOrigin: true,
}

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    proxy: {
      '/api/v1/auth': userServiceProxy,
      '/api/v1/users': userServiceProxy,
      '/api/v1/admin/users': userServiceProxy,
      '/api/v1/admin/create-admin': userServiceProxy,
      '/api/v1/todos': todoServiceProxy,
      '/api/v1/admin/todos': todoServiceProxy,
      '/api/v1/admin/reload-config': todoServiceProxy,
      '/api/v1/config': todoServiceProxy,
    },
  },
})
