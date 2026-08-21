import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import os from 'os'

const hostname = os.hostname(); // This will get the hostname of the Raspberry Pi (e.g., raspberrypi)

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
  ],
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/setupTests.js',
  },
  server: {
    host: true,
    port: 3000,
    strictPort: true,
    hmr: {
      overlay: false
    },
    proxy: {
      '/api': 'http://localhost:5000',
      '/get_location': 'http://localhost:5000',
      '/get_ph': 'http://localhost:5000',
      '/get_ph_history': 'http://localhost:5000',
      '/get_tds': 'http://localhost:5000',
      '/get_tds_history': 'http://localhost:5000',
      '/get_temperature_humidity': 'http://localhost:5000',
      '/get_temperature_humidity_history': 'http://localhost:5000',
      '/get_moisture': 'http://localhost:5000',
      '/get_moisture_data': 'http://localhost:5000',
      '/check_moisture': 'http://localhost:5000',
      '/sensor_status': 'http://localhost:5000',
      '/get_plant_status': 'http://localhost:5000',
      '/update_plant_status': 'http://localhost:5000',
      '/set_active_plant': 'http://localhost:5000',
      '/get_photo_records': 'http://localhost:5000',
      '/get_latest_photo': 'http://localhost:5000',
      '/pump/': 'http://localhost:5000',
      '/toggle_fan': 'http://localhost:5000',
      '/capture_photo': 'http://localhost:5000',
      '/start_stream': 'http://localhost:5000',
      '/stop_stream': 'http://localhost:5000',
      '/get_email_config': 'http://localhost:5000',
      '/update_email_config': 'http://localhost:5000',
      '/get_system_config': 'http://localhost:5000',
      '/update_system_config': 'http://localhost:5000',
      '/send_report_email': 'http://localhost:5000',
      '/sensor/limits': 'http://localhost:5000',
      '/get_pump_logs': 'http://localhost:5000',
      '/download_database_pdf': 'http://localhost:5000',
      '/download_database_csv': 'http://localhost:5000',
      '/update_grow_cycle_progress': 'http://localhost:5000',
      '/get_grow_cycle_status': 'http://localhost:5000',
      '/complete_cycle': 'http://localhost:5000',

      '/socket.io': {
        target: 'http://localhost:5000',
        ws: true,
        changeOrigin: true,
      },
    }
  }
})
