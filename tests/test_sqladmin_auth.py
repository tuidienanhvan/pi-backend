from app.admin.sqladmin_setup import AdminAuth, SQLADMIN_VIEWS, _is_admin_token
from app.shared.auth.models import User
from app.shared.auth.service import AuthService


def user(is_admin=False):
    return User(
        id=1,
        email="admin@pi.local",
        name="Admin",
        password_hash="x",
        is_admin=is_admin,
        is_active=True,
        is_verified=True,
    )


def test_sqladmin_registers_expected_model_views():
    names = {view.__name__ for view in SQLADMIN_VIEWS}

    assert {"TenantAdmin", "TokenAdmin", "TokenTransactionAdmin", "LicenseAdmin", "UserAdmin", "AiProviderAdmin", "AiUsageAdmin", "AdminAuditLogAdmin"}.issubset(names)


def test_admin_token_passes_sqladmin_gate():
    token, _ = AuthService.create_token(user(is_admin=True))

    assert _is_admin_token(token) is True


def test_non_admin_token_fails_sqladmin_gate():
    token, _ = AuthService.create_token(user(is_admin=False))

    assert _is_admin_token(token) is False


def test_invalid_token_fails_sqladmin_gate():
    assert _is_admin_token("not-a-jwt") is False


def test_sqladmin_auth_backend_session_key():
    auth = AdminAuth(secret_key="test-secret")

    assert auth.middlewares
