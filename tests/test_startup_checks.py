import pytest

from app import startup_checks
from app.config import Settings


def _settings(**kw):
    base = dict(
        _env_file=None,
        environment="production",
        jwt_secret="x" * 40,
        admin_api_key="y" * 24,
        smtp_host="smtp.example.com", smtp_user="u", smtp_password="p",
        database_url="postgresql+psycopg2://u:p@host/db",
        cors_origins="https://app.example.com",
    )
    base.update(kw)
    return Settings(**base)


def test_good_production_config_has_no_errors():
    errors, _ = startup_checks.collect(_settings())
    assert errors == []


def test_defaults_are_flagged_and_production_refuses_to_start():
    s = _settings(jwt_secret="CHANGE_ME_IN_PRODUCTION", admin_api_key="CHANGE_ME_ADMIN_KEY",
                  smtp_host="", database_url="sqlite:///./x.db")
    errors, _ = startup_checks.collect(s)
    assert len(errors) == 4
    with pytest.raises(RuntimeError):
        startup_checks.run(s)


def test_development_never_raises():
    s = _settings(environment="development", jwt_secret="CHANGE_ME_IN_PRODUCTION", smtp_host="")
    startup_checks.run(s)  # ไม่ raise


def test_secret_values_never_appear_in_messages():
    s = _settings(jwt_secret="short-secret-value", smtp_password="super-secret-smtp")
    errors, warnings = startup_checks.collect(s)
    text = " ".join(errors + warnings)
    assert "short-secret-value" not in text and "super-secret-smtp" not in text


def test_cors_list_parsing_and_warning():
    assert _settings(cors_origins="https://a.com, https://b.com").cors_origin_list == ["https://a.com", "https://b.com"]
    _, warnings = startup_checks.collect(_settings(cors_origins="*"))
    assert any("CORS" in w for w in warnings)
