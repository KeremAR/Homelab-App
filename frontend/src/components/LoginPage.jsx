import { useState } from 'react';

const USER_SERVICE_URL = '';  // Empty string for relative paths

const LoginPage = ({ onLogin }) => {
  const [showLogin, setShowLogin] = useState(true);
  const [authForm, setAuthForm] = useState({
    username: '',
    email: '',
    password: '',
  });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleInputChange = (e) => {
    const { name, value } = e.target;
    setError(''); // Clear error when user types
    setAuthForm(prev => ({
      ...prev,
      [name]: value
    }));
  };

  const login = async () => {
    setError('');
    setLoading(true);
    
    try {
      const response = await fetch(`${USER_SERVICE_URL}/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          username: authForm.username,
          password: authForm.password,
        }),
      });

      if (response.ok) {
        const { access_token } = await response.json();
        const userData = {
          id: 1,
          username: authForm.username,
          email: authForm.username + '@example.com',
        };

        localStorage.setItem('token', access_token);
        localStorage.setItem('user', JSON.stringify(userData));
        onLogin(access_token, userData);
      } else {
        const errorData = await response.json();
        setError(errorData.detail || 'Login failed. Please check your credentials.');
      }
    } catch (error) {
      console.error('Login failed:', error);
      setError('Network error. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const register = async () => {
    setError('');
    setLoading(true);
    
    try {
      const response = await fetch(`${USER_SERVICE_URL}/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(authForm),
      });

      if (response.ok) {
        setError('');
        alert('Registration successful! Please login.');
        setShowLogin(true);
        setAuthForm({ username: '', email: '', password: '' });
      } else {
        const errorData = await response.json();
        if (response.status === 409) {
          setError('Username or email already exists. Please try another.');
        } else {
          setError(errorData.detail || 'Registration failed. Please try again.');
        }
      }
    } catch (error) {
      console.error('Registration failed:', error);
      setError('Network error. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center">
      <div className="max-w-md w-full mx-auto">
        <div className="bg-white rounded-lg shadow-md p-6">
          <h1 className="text-2xl font-bold text-center mb-6 text-gray-900">
            DevOps Todo App
          </h1>
          <div className="flex mb-4">
            <button
              className={`flex-1 py-2 px-4 rounded-l-lg ${
                showLogin ? 'bg-blue-500 text-white' : 'bg-gray-200'
              }`}
              onClick={() => setShowLogin(true)}
            >
              Login
            </button>
            <button
              className={`flex-1 py-2 px-4 rounded-r-lg ${
                !showLogin ? 'bg-blue-500 text-white' : 'bg-gray-200'
              }`}
              onClick={() => setShowLogin(false)}
            >
              Register
            </button>
          </div>

          <div className="space-y-4">
            {/* Error Message Display */}
            {error && (
              <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">
                <p className="text-sm">{error}</p>
              </div>
            )}

            <input
              type="text"
              name="username"
              placeholder="Username"
              className="w-full p-3 border border-gray-300 rounded-lg text-gray-900 placeholder-gray-500 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              value={authForm.username}
              onChange={handleInputChange}
            />
            {!showLogin && (
              <input
                type="email"
                name="email"
                placeholder="Email"
                className="w-full p-3 border border-gray-300 rounded-lg text-gray-900 placeholder-gray-500 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                value={authForm.email}
                onChange={handleInputChange}
              />
            )}
            <input
              type="password"
              name="password"
              placeholder="Password"
              className="w-full p-3 border border-gray-300 rounded-lg text-gray-900 placeholder-gray-500 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              value={authForm.password}
              onChange={handleInputChange}
            />
            <button
              className="w-full bg-blue-500 text-white py-3 rounded-lg hover:bg-blue-600 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
              onClick={showLogin ? login : register}
              disabled={loading}
            >
              {loading ? (
                <span className="flex items-center justify-center">
                  <svg className="animate-spin h-5 w-5 mr-2" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                  {showLogin ? 'Logging in...' : 'Registering...'}
                </span>
              ) : (
                showLogin ? 'Login' : 'Register'
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default LoginPage;
