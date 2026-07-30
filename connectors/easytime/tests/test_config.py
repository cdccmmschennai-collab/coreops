"""Connector configuration loading and, above all, secret hygiene."""
from __future__ import annotations

from pathlib import Path

import pytest

from config import AUTH_PATH_CANDIDATES, EasyTimeConfig, load_config
from exceptions import EasyTimeConfigError

ENV_KEYS = [
    "EASYTIME_BASE_URL",
    "EASYTIME_USERNAME",
    "EASYTIME_PASSWORD",
    "EASYTIME_AUTH_MODE",
    "EASYTIME_AUTH_HEADER_SCHEME",
    "EASYTIME_AUTH_PATH",
    "EASYTIME_TRANSACTIONS_PATH",
    "EASYTIME_VERIFY_SSL",
    "EASYTIME_PAGE_SIZE",
    "TIMEZONE",
]


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def write_env(tmp_path: Path, body: str) -> Path:
    path = tmp_path / ".env"
    path.write_text(body, encoding="utf-8")
    return path


class TestLoad:
    def test_reads_a_complete_file(self, tmp_path):
        path = write_env(
            tmp_path,
            "EASYTIME_BASE_URL=http://127.0.0.1:8080/\n"
            "EASYTIME_USERNAME=coreops_integration\n"
            "EASYTIME_PASSWORD=s3cret\n"
            "EASYTIME_AUTH_MODE=token\n"
            "EASYTIME_PAGE_SIZE=250\n"
            "TIMEZONE=Asia/Kolkata\n",
        )

        config = load_config(path)

        assert config.base_url == "http://127.0.0.1:8080"  # trailing slash trimmed
        assert config.auth_mode == "token"
        assert config.page_size == 250
        assert config.timezone == "Asia/Kolkata"

    def test_missing_file_is_a_clear_error(self, tmp_path):
        with pytest.raises(EasyTimeConfigError) as exc:
            load_config(tmp_path / "absent.env")
        assert ".env.example" in str(exc.value)

    def test_missing_credentials_are_named(self, tmp_path):
        path = write_env(tmp_path, "EASYTIME_BASE_URL=http://127.0.0.1:8080\n")

        with pytest.raises(EasyTimeConfigError) as exc:
            load_config(path)
        assert "EASYTIME_USERNAME" in str(exc.value)
        assert "EASYTIME_PASSWORD" in str(exc.value)

    def test_check_config_mode_tolerates_empty_credentials(self, tmp_path):
        path = write_env(tmp_path, "EASYTIME_BASE_URL=http://127.0.0.1:8080\n")

        config = load_config(path, require_credentials=False)

        assert config.base_url == "http://127.0.0.1:8080"

    def test_rejects_an_unknown_auth_mode(self, tmp_path):
        path = write_env(
            tmp_path,
            "EASYTIME_BASE_URL=http://x:1\nEASYTIME_USERNAME=u\n"
            "EASYTIME_PASSWORD=p\nEASYTIME_AUTH_MODE=magic\n",
        )

        with pytest.raises(EasyTimeConfigError):
            load_config(path)

    def test_rejects_a_url_without_a_scheme(self, tmp_path):
        path = write_env(
            tmp_path,
            "EASYTIME_BASE_URL=127.0.0.1:8080\nEASYTIME_USERNAME=u\nEASYTIME_PASSWORD=p\n",
        )

        with pytest.raises(EasyTimeConfigError) as exc:
            load_config(path)
        assert "http://" in str(exc.value)


class TestPaths:
    def test_unpinned_paths_fall_back_to_candidates(self):
        config = EasyTimeConfig(base_url="http://x:1", username="u", password="p")

        assert config.auth_paths == AUTH_PATH_CANDIDATES["jwt"]
        assert len(config.transactions_paths) > 1

    def test_pinned_path_wins(self):
        config = EasyTimeConfig(
            base_url="http://x:1", username="u", password="p",
            auth_path="/custom/auth/",
        )

        assert config.auth_paths == ("/custom/auth/",)

    def test_header_scheme_defaults_per_mode(self):
        base = dict(base_url="http://x:1", username="u", password="p")

        assert EasyTimeConfig(**base, auth_mode="jwt").header_scheme == "JWT"
        assert EasyTimeConfig(**base, auth_mode="token").header_scheme == "Token"
        assert EasyTimeConfig(**base, auth_header_scheme="none").header_scheme == ""


class TestSecrets:
    def test_redacted_hides_the_password_entirely(self):
        config = EasyTimeConfig(
            base_url="http://x:1", username="coreops_integration", password="hunter2"
        )

        rendered = str(config.redacted())

        assert "hunter2" not in rendered
        assert "coreops_integration" not in rendered  # username is masked too
        assert config.redacted()["password"] == "***"

    def test_example_env_file_carries_no_real_password(self):
        # Guards the one mistake that would put a live credential in git.
        example = Path(__file__).resolve().parents[1] / ".env.example"
        for line in example.read_text(encoding="utf-8").splitlines():
            if line.startswith(("EASYTIME_PASSWORD=", "COREOPS_CONNECTOR_TOKEN=")):
                assert line.split("=", 1)[1].strip() == "", line
