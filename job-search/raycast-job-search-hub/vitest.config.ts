import { resolve } from "node:path";
import { defineConfig } from "vitest/config";

export default defineConfig({
  resolve: {
    alias: {
      "@raycast/api": resolve(__dirname, "src/__tests__/mocks/raycast-api.ts"),
    },
  },
  test: {
    environment: "node",
    globals: true,
  },
});
