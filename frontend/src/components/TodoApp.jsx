import { useState, useEffect } from 'react';

const TODO_SERVICE_URL = '';  // Empty string for relative paths

const TodoApp = ({ user, token, onLogout }) => {
  const [todos, setTodos] = useState([]);
  const [newTodo, setNewTodo] = useState({ title: '', description: '' });

  const fetchTodos = async () => {
    try {
      const response = await fetch(`${TODO_SERVICE_URL}/todos`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (response.ok) {
        const todosData = await response.json();
        setTodos(todosData);
      }
    } catch (error) {
      console.error('Failed to fetch todos:', error);
    }
  };

  useEffect(() => {
    if (token) {
      fetchTodos();
    }
  }, [token]);

  const createTodo = async () => {
    if (!newTodo.title.trim()) return;
    try {
      const response = await fetch(`${TODO_SERVICE_URL}/todos`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(newTodo),
      });
      if (response.ok) {
        const createdTodo = await response.json();
        setTodos([createdTodo, ...todos]);
        setNewTodo({ title: '', description: '' });
      } else {
        alert('Failed to create todo');
      }
    } catch (error) {
      console.error('Failed to create todo:', error);
      alert('Failed to create todo');
    }
  };

  const toggleTodo = async (todoId, completed) => {
    try {
      const response = await fetch(`${TODO_SERVICE_URL}/todos/${todoId}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ completed }),
      });
      if (response.ok) {
        const updatedTodo = await response.json();
        setTodos(todos.map((todo) =>
          todo.id === todoId ? updatedTodo : todo
        ));
      } else {
        alert('Failed to update todo');
      }
    } catch (error) {
      console.error('Failed to update todo:', error);
      alert('Failed to update todo');
    }
  };

  const deleteTodo = async (todoId) => {
    try {
      const response = await fetch(`${TODO_SERVICE_URL}/todos/${todoId}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` },
      });
      if (response.ok) {
        setTodos(todos.filter((todo) => todo.id !== todoId));
      } else {
        alert('Failed to delete todo');
      }
    } catch (error) {
      console.error('Failed to delete todo:', error);
      alert('Failed to delete todo');
    }
  };

  const logout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    onLogout();
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <nav className="bg-white shadow-sm border-b">
        <div className="max-w-4xl mx-auto px-4 py-4 flex justify-between items-center">
          <h1 className="text-2xl font-bold text-gray-900">DevOps Todo App</h1>
          {user && (
            <div className="flex items-center space-x-4">
              <span className="text-gray-600">
                Welcome, {user.username}!
              </span>
              <button
                onClick={logout}
                className="bg-red-500 text-white px-4 py-2 rounded-lg hover:bg-red-600"
              >
                Logout
              </button>
            </div>
          )}
        </div>
      </nav>

      <main className="max-w-4xl mx-auto px-4 py-8">
        <div className="bg-white rounded-lg shadow-md p-6 mb-6">
          <h3 className="text-lg font-semibold mb-4">Add New Todo</h3>
          <div className="space-y-4">
            <input
              type="text"
              placeholder="Todo title"
              className="w-full p-3 border border-gray-300 rounded-lg text-gray-900 placeholder-gray-500 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              value={newTodo.title}
              onChange={(e) => setNewTodo({ ...newTodo, title: e.target.value })}
            />
            <textarea
              placeholder="Description (optional)"
              className="w-full p-3 border border-gray-300 rounded-lg text-gray-900 placeholder-gray-500 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 resize-none"
              rows={3}
              value={newTodo.description}
              onChange={(e) => setNewTodo({ ...newTodo, description: e.target.value })}
            />
            <button
              onClick={createTodo}
              className="bg-green-500 text-white px-6 py-2 rounded-lg hover:bg-green-600"
            >
              Add Todo
            </button>
          </div>
        </div>

        <div className="space-y-4">
          {todos.map((todo) => (
            <div key={todo.id} className="bg-white rounded-lg shadow-md p-4">
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="flex items-center mb-2">
                    <input
                      type="checkbox"
                      checked={todo.completed}
                      onChange={(e) => toggleTodo(todo.id, e.target.checked)}
                      className="mr-3 h-5 w-5 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
                    />
                    <h4
                      className={`text-lg font-medium ${
                        todo.completed ? 'line-through text-gray-500' : ''
                      }`}
                    >
                      {todo.title}
                    </h4>
                  </div>
                  {todo.description && (
                    <p
                      className={`text-gray-600 ml-7 ${
                        todo.completed ? 'line-through' : ''
                      }`}
                    >
                      {todo.description}
                    </p>
                  )}
                  <p className="text-sm text-gray-400 ml-7 mt-2">
                    Created: {new Date(todo.created_at).toLocaleDateString()}
                  </p>
                </div>
                <button
                  onClick={() => deleteTodo(todo.id)}
                  className="text-red-500 hover:text-red-700 ml-4"
                >
                  Delete
                </button>
              </div>
            </div>
          ))}
          {todos.length === 0 && (
            <div className="text-center text-gray-500 py-8">
              No todos yet. Create your first todo above!
            </div>
          )}
        </div>
      </main>
    </div>
  );
};

export default TodoApp;
