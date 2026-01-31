/**
 * Vitest Configuration for Telar JavaScript Tests
 *
 * @version v0.7.0-beta
 */

import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    include: ['tests/js/**/*.test.js'],
    environment: 'jsdom',
    globals: false,
  },
});
