import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiRequest } from '../api/client'
import { useAuth } from '../auth/useAuth'

const emptyTodo = { title: '', description: '' }

export default function TodoApp() {
  const { user, logout } = useAuth()
  const queryClient = useQueryClient()
  const [newTodo, setNewTodo] = useState(emptyTodo)

  const todosQuery = useQuery({
    queryKey: ['todos'],
    queryFn: () => apiRequest('/todos'),
    enabled: Boolean(user),
  })

  const invalidateTodos = () =>
    queryClient.invalidateQueries({ queryKey: ['todos'] })

  const createMutation = useMutation({
    mutationFn: (todo) =>
      apiRequest('/todos', { method: 'POST', body: todo }),
    onSuccess: async () => {
      setNewTodo(emptyTodo)
      await invalidateTodos()
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, completed }) =>
      apiRequest('/todos/' + id, {
        method: 'PATCH',
        body: { completed },
      }),
    onSuccess: invalidateTodos,
  })

  const deleteMutation = useMutation({
    mutationFn: (todoId) =>
      apiRequest('/todos/' + todoId, { method: 'DELETE' }),
    onSuccess: invalidateTodos,
  })

  const mutationError =
    createMutation.error || updateMutation.error || deleteMutation.error

  const submitTodo = (event) => {
    event.preventDefault()
    const title = newTodo.title.trim()
    if (!title || createMutation.isPending) return

    createMutation.mutate({
      title,
      description: newTodo.description.trim() || null,
    })
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <nav className="border-b bg-white shadow-sm">
        <div className="mx-auto flex max-w-4xl items-center justify-between px-4 py-4">
          <h1 className="text-2xl font-bold text-gray-900">DevOps Todo App</h1>
          <div className="flex items-center space-x-4">
            <span className="text-gray-600">Welcome, {user.username}!</span>
            <button
              type="button"
              onClick={() => logout()}
              className="rounded-lg bg-red-500 px-4 py-2 text-white hover:bg-red-600"
            >
              Log out
            </button>
          </div>
        </div>
      </nav>

      <main className="mx-auto max-w-4xl px-4 py-8">
        <section className="mb-6 rounded-lg bg-white p-6 shadow-md">
          <h2 className="mb-4 text-lg font-semibold">Add New Todo</h2>
          <form onSubmit={submitTodo} className="space-y-4">
            <input
              type="text"
              aria-label="Todo title"
              placeholder="Todo title"
              value={newTodo.title}
              onChange={(event) =>
                setNewTodo((previous) => ({
                  ...previous,
                  title: event.target.value,
                }))
              }
              className="w-full rounded-lg border border-gray-300 p-3 text-gray-900"
            />
            <textarea
              aria-label="Todo description"
              placeholder="Description (optional)"
              rows={3}
              value={newTodo.description}
              onChange={(event) =>
                setNewTodo((previous) => ({
                  ...previous,
                  description: event.target.value,
                }))
              }
              className="w-full resize-none rounded-lg border border-gray-300 p-3 text-gray-900"
            />
            <button
              type="submit"
              disabled={createMutation.isPending}
              className="rounded-lg bg-green-500 px-6 py-2 text-white hover:bg-green-600 disabled:bg-gray-400"
            >
              {createMutation.isPending ? 'Adding...' : 'Add Todo'}
            </button>
          </form>
        </section>

        {mutationError && (
          <p role="alert" className="mb-4 rounded-lg bg-red-50 px-4 py-3 text-red-700">
            {mutationError.message}
          </p>
        )}

        {todosQuery.isPending && (
          <p role="status" className="py-8 text-center text-gray-600">
            Loading todos...
          </p>
        )}
        {todosQuery.isError && (
          <div className="rounded-lg bg-red-50 p-6 text-center text-red-700">
            <p role="alert">{todosQuery.error.message}</p>
            <button
              type="button"
              onClick={() => todosQuery.refetch()}
              className="mt-4 rounded-lg bg-red-600 px-4 py-2 text-white hover:bg-red-700"
            >
              Retry
            </button>
          </div>
        )}
        {todosQuery.isSuccess && todosQuery.data.length === 0 && (
          <p className="py-8 text-center text-gray-500">
            No todos yet. Create your first todo above!
          </p>
        )}
        {todosQuery.isSuccess && todosQuery.data.length > 0 && (
          <div className="space-y-4">
            {todosQuery.data.map((todo) => (
              <article key={todo.id} className="rounded-lg bg-white p-4 shadow-md">
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="mb-2 flex items-center">
                      <input
                        type="checkbox"
                        aria-label={'Mark ' + todo.title + ' complete'}
                        checked={todo.completed}
                        onChange={(event) =>
                          updateMutation.mutate({
                            id: todo.id,
                            completed: event.target.checked,
                          })
                        }
                        className="mr-3 h-5 w-5"
                      />
                      <h3
                        className={
                          todo.completed
                            ? 'text-lg font-medium text-gray-500 line-through'
                            : 'text-lg font-medium'
                        }
                      >
                        {todo.title}
                      </h3>
                    </div>
                    {todo.description && (
                      <p className="ml-7 text-gray-600">{todo.description}</p>
                    )}
                    <p className="ml-7 mt-2 text-sm text-gray-400">
                      Created: {new Date(todo.created_at).toLocaleDateString()}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => deleteMutation.mutate(todo.id)}
                    disabled={deleteMutation.isPending}
                    className="ml-4 text-red-500 hover:text-red-700 disabled:text-gray-400"
                  >
                    Delete
                  </button>
                </div>
              </article>
            ))}
          </div>
        )}
      </main>
    </div>
  )
}
