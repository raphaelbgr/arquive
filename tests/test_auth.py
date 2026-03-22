"""Tests for authentication: password hashing, JWT tokens, session management."""

from datetime import timedelta


class TestPasswordHashing:
    def test_hash_and_verify(self):
        from face_detect.auth import hash_password, verify_password
        h = hash_password("secret123")
        assert verify_password("secret123", h)
        assert not verify_password("wrong", h)

    def test_different_passwords_different_hashes(self):
        from face_detect.auth import hash_password
        h1 = hash_password("pass1")
        h2 = hash_password("pass2")
        assert h1 != h2


class TestJWT:
    def test_create_and_decode(self):
        from face_detect.auth import create_token, decode_token
        token = create_token({"sub": "user1", "role": "admin"}, "test-secret-key-32bytes-long!!", timedelta(hours=1))
        payload = decode_token(token, "test-secret-key-32bytes-long!!")
        assert payload["sub"] == "user1"
        assert payload["role"] == "admin"

    def test_expired_token_rejected(self):
        from face_detect.auth import create_token, decode_token
        token = create_token({"sub": "x"}, "test-secret-key-32bytes-long!!", timedelta(seconds=-1))
        assert decode_token(token, "test-secret-key-32bytes-long!!") is None

    def test_wrong_secret_rejected(self):
        from face_detect.auth import create_token, decode_token
        token = create_token({"sub": "x"}, "correct-secret-key-32bytes!!!!!", timedelta(hours=1))
        assert decode_token(token, "wrong-secret-key-that-is-32bytes") is None


class TestAuthManager:
    def test_password_flow(self, auth_manager):
        pw = auth_manager.get_or_create_password()
        assert pw is not None
        assert auth_manager.check_password(pw)
        assert not auth_manager.check_password("wrong")
        # Second call returns None (password already exists)
        assert auth_manager.get_or_create_password() is None

    def test_set_password(self, auth_manager):
        auth_manager.set_password("mypass")
        assert auth_manager.check_password("mypass")

    def test_user_account_flow(self, auth_manager):
        auth_manager.create_user("alice", "pass123", "admin")
        user = auth_manager.authenticate_user("alice", "pass123")
        assert user is not None
        assert user["role"] == "admin"
        # Wrong password
        assert auth_manager.authenticate_user("alice", "wrong") is None
        # Nonexistent user
        assert auth_manager.authenticate_user("ghost", "pass") is None

    def test_token_issuance_and_validation(self, auth_manager):
        token = auth_manager.issue_token("testuser", "viewer")
        payload = auth_manager.validate_token(token)
        assert payload is not None
        assert payload["sub"] == "testuser"
        assert payload["role"] == "viewer"

    def test_session_revocation(self, auth_manager):
        token = auth_manager.issue_token("user1", "admin")
        assert auth_manager.validate_token(token) is not None
        auth_manager.revoke_all_sessions()
        # Token issued before (or at same time as) revocation should be rejected
        assert auth_manager.validate_token(token) is None
        # Bump the clock forward so the new token's iat > cutoff
        import time; time.sleep(1.1)
        new_token = auth_manager.issue_token("user1", "admin")
        assert auth_manager.validate_token(new_token) is not None

    def test_jwt_secret_auto_generated(self, auth_manager):
        secret = auth_manager.jwt_secret
        assert len(secret) > 20


class TestDurationParsing:
    def test_days(self):
        from face_detect.auth import parse_duration
        assert parse_duration("365d").days == 365

    def test_hours(self):
        from face_detect.auth import parse_duration
        assert parse_duration("24h").total_seconds() == 86400

    def test_forever(self):
        from face_detect.auth import parse_duration
        assert parse_duration("forever").days == 36500
