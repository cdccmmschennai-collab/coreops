"""Connector configuration loading and, above all, secret hygiene."""
from __future__ import annotations

from pathlib import Path

import pytest

from config import (
    AUTH_PATH_CANDIDATES,
    COREOPS_MAX_BATCH_SIZE,
    EasyTimeConfig,
    load_config,
    load_connector_config,
    load_coreops_config,
    load_sync_config,
)
from exceptions import ConnectorConfigError, EasyTimeConfigError

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
    # Phase 3
    "COREOPS_API_URL",
    "COREOPS_CONNECTOR_TOKEN",
    "COREOPS_TIMEOUT_SECONDS",
    "COREOPS_RETRIES",
    "CONNECTOR_ID",
    "SYNC_LOOKBACK_MINUTES",
    "SYNC_RECONCILIATION_DAYS",
    "SYNC_FIRST_RUN_LOOKBACK_HOURS",
    "SYNC_MAX_RANGE_DAYS",
    "SYNC_BATCH_SIZE",
    "SYNC_STATE_PATH",
    "SYNC_LOG_DIR",
    "SYNC_LOCK_PATH",
]

EASYTIME_BLOCK = (
    "EASYTIME_BASE_URL=http://127.0.0.1\n"
    "EASYTIME_USERNAME=coreops_integration\n"
    "EASYTIME_PASSWORD=s3cret\n"
)
COREOPS_BLOCK = (
    "COREOPS_API_URL=https://coreops.example.test/api/v1\n"
    "COREOPS_CONNECTOR_TOKEN=a-long-enough-shared-secret-value\n"
    "CONNECTOR_ID=admin-pc-01\n"
)


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


# ===========================================================================
# Phase 3 configuration
# ===========================================================================

class TestCoreOpsConfig:
    def test_reads_a_complete_file(self, tmp_path):
        path = write_env(tmp_path, EASYTIME_BLOCK + COREOPS_BLOCK + "SYNC_BATCH_SIZE=250\n")

        config = load_connector_config(path)

        assert config.coreops.api_url == "https://coreops.example.test/api/v1"
        assert config.coreops.connector_id == "admin-pc-01"
        assert config.coreops.batch_size == 250
        assert config.coreops.batch_url == (
            "https://coreops.example.test/api/v1/integrations/easytime/punches/batch"
        )

    def test_a_trailing_slash_on_the_api_url_is_trimmed(self, tmp_path):
        path = write_env(
            tmp_path,
            EASYTIME_BLOCK
            + "COREOPS_API_URL=https://coreops.example.test/api/v1/\n"
            "COREOPS_CONNECTOR_TOKEN=secret-value-long-enough\n",
        )

        assert not load_connector_config(path).coreops.api_url.endswith("/")

    def test_fails_closed_without_a_token(self, tmp_path):
        path = write_env(
            tmp_path, EASYTIME_BLOCK + "COREOPS_API_URL=https://coreops.example.test/api/v1\n"
        )

        with pytest.raises(ConnectorConfigError) as exc:
            load_connector_config(path)
        assert "COREOPS_CONNECTOR_TOKEN" in str(exc.value)

    def test_fails_closed_without_an_api_url(self, tmp_path):
        path = write_env(tmp_path, EASYTIME_BLOCK + "COREOPS_CONNECTOR_TOKEN=abc\n")

        with pytest.raises(ConnectorConfigError) as exc:
            load_connector_config(path)
        assert "COREOPS_API_URL" in str(exc.value)

    def test_rejects_an_api_url_without_a_scheme(self, tmp_path):
        path = write_env(
            tmp_path,
            EASYTIME_BLOCK + "COREOPS_API_URL=coreops.example.test/api/v1\n"
            "COREOPS_CONNECTOR_TOKEN=abc\n",
        )

        with pytest.raises(ConnectorConfigError):
            load_connector_config(path)

    def test_a_batch_size_over_the_backend_limit_is_refused_at_load_time(self, tmp_path):
        # Refused here rather than as a 422 on every POST at 03:00 on a Sunday.
        path = write_env(
            tmp_path,
            EASYTIME_BLOCK + COREOPS_BLOCK + f"SYNC_BATCH_SIZE={COREOPS_MAX_BATCH_SIZE + 1}\n",
        )

        with pytest.raises(ConnectorConfigError) as exc:
            load_connector_config(path)
        assert str(COREOPS_MAX_BATCH_SIZE) in str(exc.value)

    @pytest.mark.parametrize(
        "line",
        [
            "SYNC_BATCH_SIZE=0\n",
            "COREOPS_RETRIES=0\n",
            "COREOPS_RETRIES=99\n",
            "COREOPS_TIMEOUT_SECONDS=0\n",
        ],
    )
    def test_out_of_range_values_are_refused(self, tmp_path, line):
        path = write_env(tmp_path, EASYTIME_BLOCK + COREOPS_BLOCK + line)

        with pytest.raises(ConnectorConfigError):
            load_connector_config(path)

    def test_connector_id_defaults_to_the_hostname(self, tmp_path, monkeypatch):
        path = write_env(
            tmp_path,
            EASYTIME_BLOCK
            + "COREOPS_API_URL=https://coreops.example.test/api/v1\n"
            "COREOPS_CONNECTOR_TOKEN=abcdefgh\n",
        )
        monkeypatch.setattr("config.socket.gethostname", lambda: "ADMIN-PC-42")

        assert load_connector_config(path).coreops.connector_id == "ADMIN-PC-42"

    def test_status_mode_tolerates_a_half_filled_file(self, tmp_path):
        # --status must work on the PC where .env is not finished yet: that is
        # exactly when someone runs it to find out what is wrong.
        path = write_env(tmp_path, "EASYTIME_BASE_URL=http://127.0.0.1\n")

        config = load_connector_config(path, require_credentials=False)

        assert config.coreops.connector_token == ""


class TestSyncConfig:
    def test_defaults_match_the_documented_values(self, tmp_path):
        path = write_env(tmp_path, EASYTIME_BLOCK + COREOPS_BLOCK)

        sync = load_connector_config(path).sync

        assert sync.lookback_minutes == 15
        assert sync.reconciliation_days == 7
        assert sync.first_run_lookback_hours == 24

    def test_paths_are_overridable_for_development(self, tmp_path):
        path = write_env(
            tmp_path,
            EASYTIME_BLOCK
            + COREOPS_BLOCK
            + f"SYNC_STATE_PATH={tmp_path / 'my.db'}\n"
            + f"SYNC_LOG_DIR={tmp_path / 'mylogs'}\n"
            + f"SYNC_LOCK_PATH={tmp_path / 'my.lock'}\n",
        )

        sync = load_connector_config(path).sync

        assert sync.state_path == tmp_path / "my.db"
        assert sync.log_dir == tmp_path / "mylogs"
        assert sync.lock_path == tmp_path / "my.lock"

    def test_the_lock_defaults_next_to_the_state_file(self, tmp_path, monkeypatch):
        # Two connectors pointed at different state files must not block each
        # other on a shared default lock.
        monkeypatch.setenv("SYNC_STATE_PATH", str(tmp_path / "elsewhere" / "state.db"))

        sync = load_sync_config()

        assert sync.lock_path == tmp_path / "elsewhere" / "sync.lock"

    @pytest.mark.parametrize(
        "line",
        [
            "SYNC_LOOKBACK_MINUTES=-1\n",
            "SYNC_RECONCILIATION_DAYS=0\n",
            "SYNC_RECONCILIATION_DAYS=500\n",
            "SYNC_FIRST_RUN_LOOKBACK_HOURS=0\n",
            "SYNC_MAX_RANGE_DAYS=0\n",
            "SYNC_MAX_RANGE_DAYS=1000\n",
        ],
    )
    def test_out_of_range_values_are_refused(self, tmp_path, line):
        path = write_env(tmp_path, EASYTIME_BLOCK + COREOPS_BLOCK + line)

        with pytest.raises(ConnectorConfigError):
            load_connector_config(path)

    def test_a_reconciliation_span_wider_than_the_range_limit_is_refused(self, tmp_path):
        # Otherwise the reconciliation pass could never run at all.
        path = write_env(
            tmp_path,
            EASYTIME_BLOCK + COREOPS_BLOCK
            + "SYNC_RECONCILIATION_DAYS=30\nSYNC_MAX_RANGE_DAYS=7\n",
        )

        with pytest.raises(ConnectorConfigError) as exc:
            load_connector_config(path)
        assert "could never run" in str(exc.value)

    def test_a_non_integer_value_is_refused_rather_than_defaulted(self, tmp_path):
        path = write_env(
            tmp_path, EASYTIME_BLOCK + COREOPS_BLOCK + "SYNC_LOOKBACK_MINUTES=fifteen\n"
        )

        with pytest.raises(EasyTimeConfigError):
            load_connector_config(path)


class TestPhase3Secrets:
    def test_the_redacted_view_never_carries_the_token(self, tmp_path):
        path = write_env(
            tmp_path,
            EASYTIME_BLOCK
            + "COREOPS_API_URL=https://coreops.example.test/api/v1\n"
            "COREOPS_CONNECTOR_TOKEN=super-secret-connector-token-value\n",
        )

        rendered = str(load_connector_config(path).redacted())

        assert "super-secret-connector-token-value" not in rendered
        assert "s3cret" not in rendered

    def test_the_batch_url_never_carries_the_token(self, tmp_path):
        path = write_env(
            tmp_path,
            EASYTIME_BLOCK
            + "COREOPS_API_URL=https://coreops.example.test/api/v1\n"
            "COREOPS_CONNECTOR_TOKEN=super-secret-connector-token-value\n",
        )

        config = load_connector_config(path)

        assert "super-secret" not in config.coreops.batch_url
        assert "?" not in config.coreops.batch_url

    def test_the_example_file_documents_every_phase_3_setting(self):
        """A setting that is not in .env.example does not exist to the admin."""
        example = (Path(__file__).resolve().parents[1] / ".env.example").read_text(
            encoding="utf-8"
        )
        for key in (
            "COREOPS_API_URL",
            "COREOPS_CONNECTOR_TOKEN",
            "COREOPS_TIMEOUT_SECONDS",
            "COREOPS_RETRIES",
            "CONNECTOR_ID",
            "SYNC_LOOKBACK_MINUTES",
            "SYNC_RECONCILIATION_DAYS",
            "SYNC_FIRST_RUN_LOOKBACK_HOURS",
            "SYNC_MAX_RANGE_DAYS",
            "SYNC_BATCH_SIZE",
            "SYNC_STATE_PATH",
            "SYNC_LOG_DIR",
            "SYNC_LOCK_PATH",
        ):
            assert key in example, f"{key} is undocumented in .env.example"
