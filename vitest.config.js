/**
 * Vitest Configuration for Telar JavaScript Tests
 *
 * @version v1.4.0
 */

import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    include: ['tests/js/**/*.test.js'],
    environment: 'jsdom',
    globals: false,
    setupFiles: ['tests/js/setup.js'],
  },
});
