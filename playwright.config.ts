import { defineConfig } from '@playwright/test'
export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: false,
  workers: 1,
  use: { baseURL: 'http://127.0.0.1:5180', trace: 'retain-on-failure' },
  webServer: [
    { command: 'uv run uvicorn app.main:app --app-dir apps/api --port 8010 --host 127.0.0.1', url: 'http://127.0.0.1:8010/ready', reuseExistingServer: false, env: { DATABASE_URL: 'sqlite:///./data/e2e.db', SCHEDULER_ENABLED: 'false', PROVISIONING_TOKEN: '', LLM_PROVIDER: 'disabled' } },
    { command: 'npm --prefix apps/web run dev -- --host 127.0.0.1 --port 5180', url: 'http://127.0.0.1:5180', reuseExistingServer: false, env: { METRICAIRN_API_URL: 'http://127.0.0.1:8010' } },
  ],
})
