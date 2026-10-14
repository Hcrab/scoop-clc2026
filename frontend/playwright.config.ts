import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir:'./e2e',
  workers:1,
  timeout:120_000,
  expect:{timeout:20_000},
  use:{baseURL:process.env.SCOOP_TEST_URL||'http://127.0.0.1:8009',channel:'msedge',headless:true,viewport:{width:1440,height:1000}},
});
