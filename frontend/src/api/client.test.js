import { afterEach, describe, expect, it, vi } from 'vitest'
import { apiRequest } from './client'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('apiRequest response validation', () => {
  it('rejects an HTML response even when the status is 200', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: { get: () => 'text/html' },
        text: async () => '<!doctype html><html></html>',
      }),
    )

    await expect(apiRequest('/not-a-real-endpoint')).rejects.toMatchObject({
      message: 'API returned a non-JSON response',
      status: 200,
    })
  })
})
