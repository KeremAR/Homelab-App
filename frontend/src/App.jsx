import { Link, Navigate, Outlet, Route, Routes } from 'react-router-dom'
import LoginPage from './components/LoginPage'
import TodoApp from './components/TodoApp'
import ProtectedRoute from './ProtectedRoute'
import { AuthProvider } from './auth/AuthContext'
import { useAuth } from './auth/useAuth'

function InitializationState() {
  return (
    <main className="min-h-screen flex items-center justify-center bg-gray-50">
      <p role="status" className="text-gray-600">Checking your session...</p>
    </main>
  )
}

function InitializationError() {
  const { initializationError, retrySession, logout } = useAuth()

  return (
    <main className="min-h-screen flex items-center justify-center bg-gray-50 p-6">
      <div className="max-w-md rounded-lg bg-white p-6 text-center shadow-md">
        <h1 className="text-xl font-semibold text-gray-900">
          We could not validate your session
        </h1>
        <p role="alert" className="mt-3 text-sm text-red-700">
          {initializationError?.message || 'Please try again.'}
        </p>
        <div className="mt-5 flex justify-center gap-3">
          <button
            type="button"
            onClick={retrySession}
            className="rounded-lg bg-blue-500 px-4 py-2 text-white hover:bg-blue-600"
          >
            Retry
          </button>
          <button
            type="button"
            onClick={() => logout()}
            className="rounded-lg bg-gray-200 px-4 py-2 text-gray-800 hover:bg-gray-300"
          >
            Log out
          </button>
        </div>
      </div>
    </main>
  )
}

function HomeRedirect() {
  const { isAuthenticated } = useAuth()
  return <Navigate to={isAuthenticated ? '/todos' : '/login'} replace />
}

function GuestRoute() {
  const { isAuthenticated } = useAuth()
  return isAuthenticated ? <Navigate to="/todos" replace /> : <Outlet />
}

function NotFound() {
  const { isAuthenticated } = useAuth()

  return (
    <main className="min-h-screen flex items-center justify-center bg-gray-50 p-6">
      <div className="text-center">
        <h1 className="text-3xl font-bold text-gray-900">Page not found</h1>
        <Link
          to={isAuthenticated ? '/todos' : '/login'}
          className="mt-4 inline-block text-blue-600 hover:text-blue-800"
        >
          Return to the app
        </Link>
      </div>
    </main>
  )
}

function AppRoutes() {
  const { isInitializing, initializationError } = useAuth()

  if (isInitializing) {
    return <InitializationState />
  }

  if (initializationError) {
    return <InitializationError />
  }

  return (
    <Routes>
      <Route path="/" element={<HomeRedirect />} />
      <Route element={<GuestRoute />}>
        <Route path="/login" element={<LoginPage mode="login" />} />
        <Route path="/register" element={<LoginPage mode="register" />} />
      </Route>
      <Route element={<ProtectedRoute />}>
        <Route path="/todos" element={<TodoApp />} />
      </Route>
      <Route path="*" element={<NotFound />} />
    </Routes>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <AppRoutes />
    </AuthProvider>
  )
}
