import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { apiRequest } from '../api/client'
import { useAuth } from '../auth/useAuth'

const emptyForm = { username: '', email: '', password: '' }

export default function LoginPage({ mode = 'login' }) {
  const isLogin = mode === 'login'
  const [form, setForm] = useState(emptyForm)
  const navigate = useNavigate()
  const location = useLocation()
  const { signIn } = useAuth()
  const registrationMessage = location.state?.message

  const mutation = useMutation({
    mutationFn: async () => {
      const data = await apiRequest(isLogin ? '/auth/login' : '/auth/register', {
        method: 'POST',
        body: isLogin
          ? { username: form.username, password: form.password }
          : form,
      })

      if (
        isLogin &&
        (!data ||
          typeof data.access_token !== 'string' ||
          !data.access_token.trim() ||
          typeof data.token_type !== 'string' ||
          data.token_type.toLowerCase() !== 'bearer')
      ) {
        throw new Error('Login response did not contain a valid access token.')
      }

      return data
    },
    onSuccess: (data) => {
      if (isLogin) {
        signIn(data.access_token)
        navigate('/todos', { replace: true })
      } else {
        navigate('/login', {
          replace: true,
          state: { message: 'Registration successful. Please log in.' },
        })
      }
    },
  })

  const handleSubmit = (event) => {
    event.preventDefault()
    mutation.reset()
    mutation.mutate()
  }

  const updateField = (event) => {
    const { name, value } = event.target
    setForm((previous) => ({ ...previous, [name]: value }))
    mutation.reset()
  }

  return (
    <main className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
      <div className="max-w-md w-full">
        <section className="bg-white rounded-lg shadow-md p-6">
          <h1 className="text-2xl font-bold text-center mb-6 text-gray-900">
            DevOps Todo App
          </h1>
          <h2 className="text-xl font-semibold text-gray-900">
            {isLogin ? 'Log in' : 'Create an account'}
          </h2>

          {registrationMessage && (
            <p className="mt-4 rounded-lg bg-green-50 px-4 py-3 text-sm text-green-700">
              {registrationMessage}
            </p>
          )}
          {mutation.isError && (
            <p role="alert" className="mt-4 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">
              {mutation.error.message}
            </p>
          )}

          <form onSubmit={handleSubmit} className="mt-5 space-y-4">
            <label className="block text-sm font-medium text-gray-700">
              Username
              <input
                type="text"
                name="username"
                required
                autoComplete="username"
                value={form.username}
                onChange={updateField}
                className="mt-1 w-full rounded-lg border border-gray-300 p-3 text-gray-900"
              />
            </label>

            {!isLogin && (
              <label className="block text-sm font-medium text-gray-700">
                Email
                <input
                  type="email"
                  name="email"
                  required
                  autoComplete="email"
                  value={form.email}
                  onChange={updateField}
                  className="mt-1 w-full rounded-lg border border-gray-300 p-3 text-gray-900"
                />
              </label>
            )}

            <label className="block text-sm font-medium text-gray-700">
              Password
              <input
                type="password"
                name="password"
                required
                autoComplete={isLogin ? 'current-password' : 'new-password'}
                value={form.password}
                onChange={updateField}
                className="mt-1 w-full rounded-lg border border-gray-300 p-3 text-gray-900"
              />
            </label>

            <button
              type="submit"
              disabled={mutation.isPending}
              className="w-full rounded-lg bg-blue-500 py-3 text-white hover:bg-blue-600 disabled:cursor-not-allowed disabled:bg-gray-400"
            >
              {mutation.isPending
                ? isLogin
                  ? 'Logging in...'
                  : 'Registering...'
                : isLogin
                  ? 'Log in'
                  : 'Register'}
            </button>
          </form>

          <p className="mt-5 text-center text-sm text-gray-600">
            {isLogin ? 'Need an account?' : 'Already have an account?'}{' '}
            <Link
              to={isLogin ? '/register' : '/login'}
              className="font-medium text-blue-600 hover:text-blue-800"
            >
              {isLogin ? 'Register' : 'Log in'}
            </Link>
          </p>
        </section>
      </div>
    </main>
  )
}
