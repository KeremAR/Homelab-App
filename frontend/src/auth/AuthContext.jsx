import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { apiRequest, clearStoredToken, getStoredToken, setUnauthorizedHandler, storeToken } from '../api/client'
import { AuthContext } from './context'

export function AuthProvider({ children }) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [token, setToken] = useState(() => getStoredToken())

  const logout = useCallback(
    ({ redirect = true } = {}) => {
      clearStoredToken()
      setToken(null)
      queryClient.removeQueries({ queryKey: ['session'] })
      queryClient.removeQueries({ queryKey: ['todos'] })

      if (redirect) {
        navigate('/login', { replace: true })
      }
    },
    [navigate, queryClient],
  )

  const sessionQuery = useQuery({
    queryKey: ['session'],
    queryFn: () => apiRequest('/auth/me', { token }),
    enabled: Boolean(token),
    retry: false,
    staleTime: 5 * 60 * 1000,
  })

  useEffect(() => setUnauthorizedHandler(logout), [logout])

  const signIn = useCallback(
    (accessToken) => {
      storeToken(accessToken)
      queryClient.removeQueries({ queryKey: ['session'] })
      setToken(accessToken)
    },
    [queryClient],
  )

  const retrySession = useCallback(() => sessionQuery.refetch(), [sessionQuery])
  const initializationError =
    token && sessionQuery.isError && sessionQuery.error?.status !== 401
      ? sessionQuery.error
      : null

  const value = useMemo(
    () => ({
      token,
      user: sessionQuery.data ?? null,
      isAuthenticated: Boolean(token && sessionQuery.data),
      isInitializing: Boolean(token && sessionQuery.isPending),
      initializationError,
      retrySession,
      signIn,
      logout,
    }),
    [
      initializationError,
      logout,
      retrySession,
      sessionQuery.data,
      sessionQuery.isPending,
      signIn,
      token,
    ],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
