import { useState, useEffect } from 'react';
import LoginPage from './components/LoginPage';
import TodoApp from './components/TodoApp';

function App() {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState('');

  // Check for existing auth on app load
  useEffect(() => {
    const storedToken = localStorage.getItem('token');
    const storedUser = localStorage.getItem('user');

    if (storedToken && storedUser) {
      setToken(storedToken);
      setUser(JSON.parse(storedUser));
    }
  }, []);

  const handleLogin = (authToken, userData) => {
    setToken(authToken);
    setUser(userData);
  };
 
  
  const handleLogout = () => {
    setToken('');
    setUser(null);
  };


  
  return (
    <div className="App">
      {user && token ? (
        <TodoApp user={user} token={token} onLogout={handleLogout} />
      ) : (
        <LoginPage onLogin={handleLogin} />
      )}
    </div>
  );
}

export default App;
