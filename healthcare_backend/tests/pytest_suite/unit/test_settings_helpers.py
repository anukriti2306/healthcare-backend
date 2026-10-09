"""Unit tests for the environment helpers in config.settings."""
import pytest
from django.core.exceptions import ImproperlyConfigured

from config.settings import env_bool, env_list, env_required

KEY = "HEALTHCARE_TEST_VARIABLE"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv(KEY, raising=False)


class TestEnvRequired:
    def test_returns_the_value(self, monkeypatch):
        monkeypatch.setenv(KEY, "abc")
        assert env_required(KEY) == "abc"

    @pytest.mark.parametrize("value", [None, ""], ids=["unset", "empty"])
    def test_fails_loudly_when_missing(self, monkeypatch, value):
        if value is not None:
            monkeypatch.setenv(KEY, value)
        with pytest.raises(ImproperlyConfigured) as exc_info:
            env_required(KEY)
        # The message must tell the developer what to fix.
        assert KEY in str(exc_info.value)
        assert ".env" in str(exc_info.value)


class TestEnvBool:
    @pytest.mark.parametrize("raw", ["1", "true", "True", "YES", "on", "  true  "])
    def test_truthy_values(self, monkeypatch, raw):
        monkeypatch.setenv(KEY, raw)
        assert env_bool(KEY) is True

    @pytest.mark.parametrize("raw", ["0", "false", "no", "off", "", "maybe"])
    def test_everything_else_is_false(self, monkeypatch, raw):
        monkeypatch.setenv(KEY, raw)
        assert env_bool(KEY) is False

    @pytest.mark.parametrize("default", [True, False])
    def test_default_when_unset(self, default):
        assert env_bool(KEY, default) is default

    def test_unset_defaults_to_false_so_production_is_safe(self):
        assert env_bool(KEY) is False


class TestEnvList:
    def test_splits_and_strips(self, monkeypatch):
        monkeypatch.setenv(KEY, " a.com , b.com,c.com ")
        assert env_list(KEY) == ["a.com", "b.com", "c.com"]

    def test_drops_empty_items(self, monkeypatch):
        monkeypatch.setenv(KEY, "a.com,, ,b.com,")
        assert env_list(KEY) == ["a.com", "b.com"]

    def test_uses_default_when_unset(self):
        assert env_list(KEY, "x,y") == ["x", "y"]

    def test_empty_when_nothing_given(self):
        assert env_list(KEY) == []
