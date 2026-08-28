import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react-swc'

const userServiceProxy = {
  target: 'http://localhost:8001',
  changeOrigin: true,
}

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    proxy: {
      '/login': userServiceProxy,
      '/register': userServiceProxy,
      '/users': userServiceProxy,
      '/verify': userServiceProxy,
      '/todos': {
        target: 'http://localhost:8002',
        changeOrigin: true,
      },
    },
  },
})
