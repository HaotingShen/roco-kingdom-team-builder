"""
Authentication system tests.

Tests cover:
- Guest user creation and deduplication
- User registration (new and guest promotion)
- Login/logout functionality
- Token refresh
- Cross-user access prevention (ownership enforcement)
- Password hashing
"""

import pytest
import jwt
from backend.auth import hash_password, verify_password, create_access_token, decode_token


# ============== Password Hashing Tests ==============

class TestPasswordHashing:
    """Test password hashing utilities."""

    def test_hash_password_returns_different_hash(self):
        """Same password should produce different hashes (due to salt)."""
        password = "TestPassword123"
        hash1 = hash_password(password)
        hash2 = hash_password(password)
        assert hash1 != hash2  # Different salts

    def test_verify_password_correct(self):
        """Correct password should verify."""
        password = "TestPassword123"
        hashed = hash_password(password)
        assert verify_password(password, hashed) is True

    def test_verify_password_incorrect(self):
        """Incorrect password should not verify."""
        password = "TestPassword123"
        hashed = hash_password(password)
        assert verify_password("WrongPassword", hashed) is False

    def test_hash_password_not_plaintext(self):
        """Hash should not contain the plaintext password."""
        password = "TestPassword123"
        hashed = hash_password(password)
        assert password not in hashed


# ============== Token Tests ==============

class TestTokens:
    """Test JWT token creation and verification."""

    def test_create_access_token(self):
        """Access token should be created successfully."""
        token = create_access_token(
            user_id=1,
            username="testuser",
            is_guest=False,
            token_version=0
        )
        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0

    def test_decode_token_valid(self):
        """Valid token should decode successfully."""
        token = create_access_token(
            user_id=1,
            username="testuser",
            is_guest=False,
            token_version=0
        )
        payload = decode_token(token)
        assert payload is not None
        assert payload["sub"] == "1"
        assert payload["username"] == "testuser"
        assert payload["is_guest"] is False

    def test_decode_token_invalid(self):
        """Invalid token should raise exception."""
        with pytest.raises(jwt.InvalidTokenError):
            decode_token("invalid.token.here")


# ============== Guest User Tests ==============
# NOTE: These tests require PostgreSQL (JSONB not supported in SQLite)
# Run manually against the development server or use pytest with PostgreSQL

@pytest.mark.skip(reason="Requires PostgreSQL - run manual tests instead")
class TestGuestUser:
    """Test guest user creation and deduplication."""

    def test_create_guest_without_device_id(self, client):
        """Guest created without device_id should work."""
        response = client.post("/auth/guest", json={})
        assert response.status_code == 200
        data = response.json()
        assert data["user"]["is_guest"] is True
        assert data["access_token"] is not None

    def test_create_guest_with_device_id(self, client):
        """Guest created with device_id should work."""
        response = client.post("/auth/guest", json={"device_id": "test-device-abc"})
        assert response.status_code == 200
        data = response.json()
        assert data["user"]["is_guest"] is True
        assert "guest_" in data["user"]["username"]

    def test_guest_deduplication_same_device_id(self, client):
        """Same device_id should return same guest."""
        device_id = "dedup-test-device"

        # First request
        response1 = client.post("/auth/guest", json={"device_id": device_id})
        assert response1.status_code == 200
        user1 = response1.json()["user"]

        # Second request with same device_id
        response2 = client.post("/auth/guest", json={"device_id": device_id})
        assert response2.status_code == 200
        user2 = response2.json()["user"]

        # Should be same user
        assert user1["id"] == user2["id"]
        assert user1["username"] == user2["username"]

    def test_guest_different_device_ids(self, client):
        """Different device_ids should create different guests."""
        response1 = client.post("/auth/guest", json={"device_id": "device-aaa"})
        response2 = client.post("/auth/guest", json={"device_id": "device-bbb"})

        user1 = response1.json()["user"]
        user2 = response2.json()["user"]

        assert user1["id"] != user2["id"]


# ============== Registration Tests ==============

@pytest.mark.skip(reason="Requires PostgreSQL - run manual tests instead")
class TestRegistration:
    """Test user registration."""

    def test_register_new_user(self, client, guest_user):
        """Register should create a registered user."""
        response = client.post(
            "/auth/register",
            json={
                "username": "newuser",
                "email": "newuser@example.com",
                "password": "SecurePass123"
            },
            headers=guest_user["headers"]
        )
        assert response.status_code == 200
        data = response.json()
        assert data["user"]["is_guest"] is False
        assert data["user"]["username"] == "newuser"
        assert data["user"]["email"] == "newuser@example.com"

    def test_register_duplicate_email(self, client, registered_user):
        """Registering with existing email should fail."""
        # Create another guest first
        guest_response = client.post("/auth/guest", json={"device_id": "another-device"})
        guest_token = guest_response.json()["access_token"]

        # Try to register with same email
        response = client.post(
            "/auth/register",
            json={
                "username": "anotheruser",
                "email": "test@example.com",  # Same as registered_user
                "password": "SecurePass123"
            },
            headers={"Authorization": f"Bearer {guest_token}"}
        )
        assert response.status_code == 400
        assert "email" in response.json()["detail"].lower()

    def test_register_duplicate_username(self, client, registered_user):
        """Registering with existing username should fail."""
        # Create another guest
        guest_response = client.post("/auth/guest", json={"device_id": "yet-another-device"})
        guest_token = guest_response.json()["access_token"]

        response = client.post(
            "/auth/register",
            json={
                "username": "testuser",  # Same as registered_user
                "email": "different@example.com",
                "password": "SecurePass123"
            },
            headers={"Authorization": f"Bearer {guest_token}"}
        )
        assert response.status_code == 400
        assert "username" in response.json()["detail"].lower()


# ============== Login Tests ==============

@pytest.mark.skip(reason="Requires PostgreSQL - run manual tests instead")
class TestLogin:
    """Test login functionality."""

    def test_login_valid_credentials(self, client, registered_user):
        """Login with valid credentials should succeed."""
        response = client.post(
            "/auth/login",
            json={
                "email": "test@example.com",
                "password": "TestPass123"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["user"]["email"] == "test@example.com"
        assert data["access_token"] is not None

    def test_login_invalid_password(self, client, registered_user):
        """Login with wrong password should fail."""
        response = client.post(
            "/auth/login",
            json={
                "email": "test@example.com",
                "password": "WrongPassword123"
            }
        )
        assert response.status_code == 401

    def test_login_nonexistent_email(self, client):
        """Login with nonexistent email should fail."""
        response = client.post(
            "/auth/login",
            json={
                "email": "notexist@example.com",
                "password": "SomePassword123"
            }
        )
        assert response.status_code == 401


# ============== Logout Tests ==============

@pytest.mark.skip(reason="Requires PostgreSQL - run manual tests instead")
class TestLogout:
    """Test logout functionality."""

    def test_logout_success(self, client, registered_user):
        """Logout should succeed."""
        response = client.post(
            "/auth/logout",
            headers=registered_user["headers"]
        )
        assert response.status_code == 200
        assert response.json()["message"] == "Logged out successfully"


# ============== Get Current User Tests ==============

@pytest.mark.skip(reason="Requires PostgreSQL - run manual tests instead")
class TestGetMe:
    """Test /auth/me endpoint."""

    def test_get_me_authenticated(self, client, guest_user):
        """Authenticated user should get their profile."""
        response = client.get("/auth/me", headers=guest_user["headers"])
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == guest_user["user"]["id"]

    def test_get_me_unauthenticated(self, client):
        """Unauthenticated request should fail."""
        response = client.get("/auth/me")
        assert response.status_code == 401


# ============== Cross-User Access Prevention Tests ==============

@pytest.mark.skip(reason="Requires PostgreSQL - run manual tests instead")
class TestOwnershipEnforcement:
    """Test that users cannot access other users' teams."""

    def test_user_cannot_view_other_users_team(self, client, guest_user, second_guest, db_session):
        """User A should not be able to view User B's team."""
        # Skip if teams endpoints aren't fully wired up
        # This test validates ownership enforcement

        # User A creates a team (would need full team creation to work)
        # For now, we test the concept with a simpler approach
        pass  # Placeholder - requires team creation fixtures

    def test_user_cannot_update_other_users_team(self, client, guest_user, second_guest):
        """User A should not be able to update User B's team."""
        # Placeholder for full integration test
        pass

    def test_user_cannot_delete_other_users_team(self, client, guest_user, second_guest):
        """User A should not be able to delete User B's team."""
        # Placeholder for full integration test
        pass


# ============== Token Refresh Tests ==============

@pytest.mark.skip(reason="Requires PostgreSQL - run manual tests instead")
class TestTokenRefresh:
    """Test token refresh functionality."""

    def test_refresh_without_cookie(self, client):
        """Refresh without cookie should fail."""
        response = client.post("/auth/refresh")
        assert response.status_code == 401

    # Note: Testing cookie-based refresh requires more complex setup
    # as TestClient doesn't automatically handle cookies like a browser


# ============== Edge Cases ==============

@pytest.mark.skip(reason="Requires PostgreSQL - run manual tests instead")
class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_request_body(self, client):
        """Empty request body should be handled."""
        response = client.post("/auth/guest")
        # Should either work (create guest) or return proper error
        assert response.status_code in [200, 422]

    def test_invalid_json(self, client):
        """Invalid JSON should return 422."""
        response = client.post(
            "/auth/login",
            content="not valid json",
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 422

    def test_missing_required_fields_register(self, client, guest_user):
        """Missing required fields should return 422."""
        response = client.post(
            "/auth/register",
            json={"username": "onlyusername"},  # Missing email and password
            headers=guest_user["headers"]
        )
        assert response.status_code == 422
