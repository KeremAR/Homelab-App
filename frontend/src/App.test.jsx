import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import App from './App'

function jsonResponse(body, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: { get: () => 'application/json' },
    text: async () => JSON.stringify(body),
  }
}

function renderApp(initialPath = '/todos') {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialPath]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const authenticatedUser = {
  id: 1,
  username: 'alice',
  email: 'alice@example.com',
}

const todo = {
  id: 1,
  title: 'Existing todo',
  description: 'A saved item',
  completed: false,
  user_id: 1,
  created_at: '2026-01-01 12:00:00',
}

describe('application authentication and todo flow', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.stubGlobal('fetch', vi.fn())
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  it('validates a stored token and loads the authenticated session', async () => {
    localStorage.setItem('token', 'valid-token')
    fetch
      .mockResolvedValueOnce(jsonResponse(authenticatedUser))
      .mockResolvedValueOnce(jsonResponse([]))

    renderApp()

    expect(await screen.findByText('Welcome, alice!')).toBeInTheDocument()
    expect(fetch).toHaveBeenNthCalledWith(
      1,
      '/api/v1/auth/me',
      expect.objectContaining({
        headers: { Authorization: 'Bearer valid-token' },
      }),
    )
    expect(
      await screen.findByText('No todos yet. Create your first todo above!'),
    ).toBeInTheDocument()
  })

  it('clears an invalid stored token and redirects to login', async () => {
    localStorage.setItem('token', 'expired-token')
    fetch.mockResolvedValueOnce(jsonResponse({ detail: 'Invalid token' }, 401))

    renderApp()

    expect(await screen.findByRole('heading', { name: 'Log in' })).toBeInTheDocument()
    expect(localStorage.getItem('token')).toBeNull()
  })

  it('redirects to login when a todo operation returns 401', async () => {
    localStorage.setItem('token', 'valid-token')
    fetch
      .mockResolvedValueOnce(jsonResponse(authenticatedUser))
      .mockResolvedValueOnce(jsonResponse([todo]))
      .mockResolvedValueOnce(jsonResponse({ detail: 'Token expired' }, 401))

    renderApp()

    const checkbox = await screen.findByRole('checkbox', {
      name: 'Mark Existing todo complete',
    })
    fireEvent.click(checkbox)

    expect(await screen.findByRole('heading', { name: 'Log in' })).toBeInTheDocument()
    expect(localStorage.getItem('token')).toBeNull()
  })

  it('protects the todos route when no token is present', async () => {
    renderApp()

    expect(await screen.findByRole('heading', { name: 'Log in' })).toBeInTheDocument()
    expect(fetch).not.toHaveBeenCalled()
  })

  it('loads todos and invalidates the query after create, update, and delete', async () => {
    localStorage.setItem('token', 'valid-token')
    const createdTodo = {
      ...todo,
      id: 2,
      title: 'Created todo',
      description: null,
    }
    const updatedTodo = { ...todo, completed: true }

    fetch
      .mockResolvedValueOnce(jsonResponse(authenticatedUser))
      .mockResolvedValueOnce(jsonResponse([todo]))
      .mockResolvedValueOnce(jsonResponse(createdTodo))
      .mockResolvedValueOnce(jsonResponse([createdTodo, todo]))
      .mockResolvedValueOnce(jsonResponse(updatedTodo))
      .mockResolvedValueOnce(jsonResponse([createdTodo, updatedTodo]))
      .mockResolvedValueOnce(jsonResponse({ message: 'Todo deleted successfully' }))
      .mockResolvedValueOnce(jsonResponse([updatedTodo]))

    renderApp()

    expect(await screen.findByText('Existing todo')).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Todo title'), {
      target: { value: 'Created todo' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Add Todo' }))
    expect(await screen.findByText('Created todo')).toBeInTheDocument()

    fireEvent.click(
      screen.getByRole('checkbox', { name: 'Mark Existing todo complete' }),
    )
    await waitFor(() =>
      expect(screen.getByRole('checkbox', { name: 'Mark Existing todo complete' })).toBeChecked(),
    )

    const deleteButtons = screen.getAllByRole('button', { name: 'Delete' })
    fireEvent.click(deleteButtons[0])
    await waitFor(() =>
      expect(screen.queryByText('Created todo')).not.toBeInTheDocument(),
    )

    expect(fetch).toHaveBeenCalledTimes(8)
    expect(fetch.mock.calls[2][0]).toBe('/api/v1/todos')
    expect(fetch.mock.calls[4][0]).toBe('/api/v1/todos/1')
    expect(fetch.mock.calls[4][1].method).toBe('PATCH')
    expect(fetch.mock.calls[6][0]).toBe('/api/v1/todos/2')
    expect(fetch.mock.calls[6][1].method).toBe('DELETE')
  })
})
