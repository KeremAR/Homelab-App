const API_PREFIX = '/api/v1'

let unauthorizedHandler = null

export class ApiError extends Error {
  constructor(message, { status, detail, body } = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
    this.body = body
  }
}

export function getStoredToken() {
  return localStorage.getItem('token')
}

export function storeToken(token) {
  localStorage.setItem('token', token)
}

export function clearStoredToken() {
  localStorage.removeItem('token')
  // Remove the legacy fabricated user record during the API migration.
  localStorage.removeItem('user')
}

export function setUnauthorizedHandler(handler) {
  unauthorizedHandler = handler
  return () => {
    if (unauthorizedHandler === handler) {
      unauthorizedHandler = null
    }
  }
}

function apiUrl(path) {
  const normalizedPath = path.startsWith('/') ? path : '/' + path
  return normalizedPath.startsWith(API_PREFIX)
    ? normalizedPath
    : API_PREFIX + normalizedPath
}

function detailMessage(detail) {
  if (typeof detail === 'string') {
    return detail
  }

  if (Array.isArray(detail)) {
    return detail
      .map((item) => (typeof item === 'string' ? item : item?.msg || 'Request validation failed'))
      .join('; ')
  }

  if (detail && typeof detail === 'object') {
    return detail.message || JSON.stringify(detail)
  }

  return null
}

async function readResponseBody(response) {
  if (response.status === 204) {
    return null
  }

  const text = await response.text()
  if (!text) {
    return null
  }

  try {
    return JSON.parse(text)
  } catch {
    return text
  }
}

export async function apiRequest(path, options = {}) {
  const { token, body, headers: customHeaders = {}, ...fetchOptions } = options
  const activeToken = token ?? getStoredToken()
  const headers = { ...customHeaders }

  if (body !== undefined && !(body instanceof FormData)) {
    headers['Content-Type'] = 'application/json'
  }

  if (activeToken) {
    headers.Authorization = 'Bearer ' + activeToken
  }

  const response = await fetch(apiUrl(path), {
    ...fetchOptions,
    headers,
    body:
      body !== undefined && typeof body !== 'string'
        ? JSON.stringify(body)
        : body,
  })
  const responseBody = await readResponseBody(response)

  if (response.status === 401) {
    clearStoredToken()
    unauthorizedHandler?.()
  }

  if (!response.ok) {
    const detail = responseBody?.detail ?? responseBody
    throw new ApiError(
      detailMessage(detail) || 'Request failed with status ' + response.status,
      { status: response.status, detail, body: responseBody },
    )
  }

  return responseBody
}
