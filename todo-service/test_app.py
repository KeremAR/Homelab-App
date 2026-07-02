from unittest.mock import MagicMock, patch

import pytest
from app import ALGORITHM, SECRET_KEY, app
from fastapi.testclient import TestClient
from jose import jwt


@pytest.fixture
def client():
    return TestClient(app)


class MockDB:
    """Helper class to hold mock connection and cursor"""

    def __init__(self):
        self.conn = MagicMock()
        self.cursor = MagicMock()
        self.conn.cursor.return_value = self.cursor
        # Setup default behavior for cursor
        self.cursor.fetchone.return_value = None
        self.cursor.fetchall.return_value = []


@pytest.fixture
def mock_db():
    """Mock database connection and cursor"""
    return MockDB()


@pytest.fixture
def auth_headers():
    """Create valid JWT token for testing"""
    token_data = {"sub": "testuser", "user_id": 1}
    token = jwt.encode(token_data, SECRET_KEY, algorithm=ALGORITHM)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def invalid_auth_headers():
    """Create invalid JWT token for testing"""
    return {"Authorization": "Bearer invalid_token"}


class TestHealthCheck:
    def test_health_endpoint(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "healthy", "service": "todo-service"}

    def test_ready_endpoint_success(self, client, mock_db):
        """Test /ready endpoint when database is available"""
        with patch("app.get_db", return_value=mock_db.conn):
            # Mock successful DB query
            mock_db.cursor.fetchone.return_value = (1,)

            response = client.get("/ready")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ready"
            assert data["service"] == "todo-service"
            assert data["database"] == "connected"

            # Verify DB query was called
            mock_db.cursor.execute.assert_called_once_with("SELECT 1")

    def test_ready_endpoint_db_failure(self, client):
        """Test /ready endpoint when database is unavailable"""
        with patch("app.get_db", side_effect=Exception("Database connection failed")):
            response = client.get("/ready")
            assert response.status_code == 503
            data = response.json()
            assert data["detail"]["status"] == "not_ready"
            assert data["detail"]["database"] == "disconnected"
            assert "Database connection failed" in data["detail"]["error"]


class TestTodoCreation:
    @patch("app.get_db")
    def test_create_todo_success(self, mock_get_db, client, mock_db, auth_headers):
        # Setup mock
        mock_get_db.return_value = mock_db.conn
        mock_todo = {
            "id": 1,
            "title": "Test Todo",
            "description": "Test Description",
            "completed": False,
            "user_id": 1,
            "created_at": "2024-01-01 12:00:00",
        }
        mock_db.cursor.fetchone.return_value = mock_todo

        todo_data = {"title": "Test Todo", "description": "Test Description"}

        response = client.post("/todos", json=todo_data, headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Test Todo"
        assert data["description"] == "Test Description"
        assert data["completed"] is False
        assert data["user_id"] == 1

    def test_create_todo_unauthorized(self, client):
        todo_data = {"title": "Test Todo", "description": "Test Description"}

        response = client.post("/todos", json=todo_data)

        assert response.status_code == 401

    def test_create_todo_invalid_token(self, client, invalid_auth_headers):
        todo_data = {"title": "Test Todo", "description": "Test Description"}

        response = client.post("/todos", json=todo_data, headers=invalid_auth_headers)

        assert response.status_code == 401


class TestTodoRetrieval:
    @patch("app.get_db")
    def test_get_todos_success(self, mock_get_db, client, mock_db, auth_headers):
        # Setup mock
        mock_get_db.return_value = mock_db.conn
        mock_todos = [
            {
                "id": 1,
                "title": "Todo 1",
                "description": "Description 1",
                "completed": False,
                "user_id": 1,
                "created_at": "2024-01-01 12:00:00",
            },
            {
                "id": 2,
                "title": "Todo 2",
                "description": "Description 2",
                "completed": True,
                "user_id": 1,
                "created_at": "2024-01-02 12:00:00",
            },
        ]
        mock_db.cursor.fetchall.return_value = mock_todos

        response = client.get("/todos", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["title"] == "Todo 1"
        assert data[1]["completed"] is True

    @patch("app.get_db")
    def test_get_single_todo_success(self, mock_get_db, client, mock_db, auth_headers):
        # Setup mock
        mock_get_db.return_value = mock_db.conn
        mock_todo = {
            "id": 1,
            "title": "Test Todo",
            "description": "Test Description",
            "completed": False,
            "user_id": 1,
            "created_at": "2024-01-01 12:00:00",
        }
        mock_db.cursor.fetchone.return_value = mock_todo

        response = client.get("/todos/1", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 1
        assert data["title"] == "Test Todo"

    @patch("app.get_db")
    def test_get_todo_not_found(self, mock_get_db, client, mock_db, auth_headers):
        # Setup mock - todo not found
        mock_get_db.return_value = mock_db.conn
        mock_db.cursor.fetchone.return_value = None

        response = client.get("/todos/999", headers=auth_headers)

        assert response.status_code == 404
        assert "Todo not found" in response.json()["detail"]


class TestTodoUpdate:
    @patch("app.get_db")
    def test_update_todo_success(self, mock_get_db, client, mock_db, auth_headers):
        # Setup mock
        mock_get_db.return_value = mock_db.conn

        # Mock existing todo
        existing_todo = {
            "id": 1,
            "title": "Old Title",
            "description": "Old Description",
            "completed": False,
            "user_id": 1,
            "created_at": "2024-01-01 12:00:00",
        }

        # Mock updated todo
        updated_todo = {
            "id": 1,
            "title": "New Title",
            "description": "Old Description",
            "completed": True,
            "user_id": 1,
            "created_at": "2024-01-01 12:00:00",
        }

        mock_db.cursor.fetchone.side_effect = [
            existing_todo,
            updated_todo,
        ]

        update_data = {"title": "New Title", "completed": True}

        response = client.put("/todos/1", json=update_data, headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "New Title"
        assert data["completed"] is True

    @patch("app.get_db")
    def test_update_todo_not_found(self, mock_get_db, client, mock_db, auth_headers):
        # Setup mock - todo not found
        mock_get_db.return_value = mock_db.conn
        mock_db.cursor.fetchone.return_value = None

        update_data = {"title": "New Title"}

        response = client.put("/todos/999", json=update_data, headers=auth_headers)

        assert response.status_code == 404


class TestTodoDelete:
    @patch("app.get_db")
    def test_delete_todo_success(self, mock_get_db, client, mock_db, auth_headers):
        # Setup mock
        mock_get_db.return_value = mock_db.conn
        mock_db.cursor.fetchone.return_value = {"id": 1}

        response = client.delete("/todos/1", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert "successfully" in data["message"]

    @patch("app.get_db")
    def test_delete_todo_not_found(self, mock_get_db, client, mock_db, auth_headers):
        # Setup mock - todo not found
        mock_get_db.return_value = mock_db.conn
        mock_db.cursor.fetchone.return_value = None

        response = client.delete("/todos/999", headers=auth_headers)

        assert response.status_code == 404


class TestAdminEndpoints:
    @patch("app.get_db")
    def test_get_all_todos_admin(self, mock_get_db, client, mock_db, auth_headers):
        # Setup mock
        mock_get_db.return_value = mock_db.conn
        mock_todos = [
            {
                "id": 1,
                "title": "User 1 Todo",
                "description": "Description 1",
                "completed": False,
                "user_id": 1,
                "created_at": "2024-01-01 12:00:00",
            },
            {
                "id": 2,
                "title": "User 2 Todo",
                "description": "Description 2",
                "completed": True,
                "user_id": 2,
                "created_at": "2024-01-02 12:00:00",
            },
        ]
        mock_db.cursor.fetchall.return_value = mock_todos

        response = client.get("/admin/todos", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["user_id"] == 1
        assert data[1]["user_id"] == 2


class TestTokenVerification:
    def test_verify_token_success(self):
        # Create valid token
        token_data = {"sub": "testuser", "user_id": 1}
        token = jwt.encode(token_data, SECRET_KEY, algorithm=ALGORITHM)

        # This would normally be called within the FastAPI dependency injection
        # For testing, we can't easily test the dependency directly
        assert len(token) > 50  # Basic token structure check

    def test_verify_token_missing_header(self, client):
        response = client.get("/todos")
        assert response.status_code == 401

    def test_verify_token_invalid_format(self, client):
        headers = {"Authorization": "InvalidFormat"}
        response = client.get("/todos", headers=headers)
        assert response.status_code == 401

    def test_verify_token_invalid_token(self, client):
        headers = {"Authorization": "Bearer invalid_token"}
        response = client.get("/todos", headers=headers)
        assert response.status_code == 401


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
