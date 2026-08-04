"""Connector configuration loading and, above all, secret hygiene."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

import config as config_module
from config import (
    AUTH_PATH_CANDIDATES,
    COREOPS_MAX_BATCH_SIZE,
    DATA_ROOT_OVERRIDE_VAR,
    ENV_FILE_OVERRIDE_VAR,
    INSTALLED_CONFIG_FILENAME,
    EasyTimeConfig,
    installed_config_path,
    load_config,
    load_connector_config,
    load_coreops_config,
    load_sync_config,
    resolve_env_path,
)
from exceptions import ConnectorConfigError, EasyTimeConfigError

ENV_KEYS = [
    # The explicit path overrides. Cleared first: a value left in the ambient
    # environment would silently redirect every test below.
    ENV_FILE_OVERRIDE_VAR,
    DATA_ROOT_OVERRIDE_VAR,
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


# ===========================================================================
# Where the configuration file is read from
#
# The whole point of the installed layout is that this answer never depends on
# the caller's current directory. These tests pin the four resolution rules and
# their order.
# ===========================================================================

@pytest.fixture()
def isolated_roots(tmp_path, monkeypatch):
    """Repoint both roots at tmp_path so no test can see a real installation.

    Returns (local_env, installed_env). Neither exists yet - a test creates
    whichever one it is about.
    """
    local_env = tmp_path / "checkout" / ".env"
    local_env.parent.mkdir(parents=True, exist_ok=True)
    program_data = tmp_path / "ProgramData" / "CoreOps" / "EasyTimeConnector"

    monkeypatch.setattr(config_module, "ENV_PATH", local_env)
    monkeypatch.setattr(config_module, "PROGRAM_DATA_DIR", program_data)
    return local_env, program_data / "config" / INSTALLED_CONFIG_FILENAME


class TestEnvPathResolution:
    def test_installed_layout_resolves_to_programdata_connector_env(self, isolated_roots):
        _local, installed = isolated_roots
        installed.parent.mkdir(parents=True, exist_ok=True)
        installed.write_text(EASYTIME_BLOCK + COREOPS_BLOCK, encoding="utf-8")

        path, source = resolve_env_path()

        assert path == installed
        assert path.name == "connector.env"
        assert "installed" in source
        # And the file is actually read, not merely named.
        assert load_connector_config().coreops.connector_id == "admin-pc-01"

    def test_the_installed_path_is_used_even_when_the_file_is_absent(self, isolated_roots):
        # Nothing exists anywhere: the default must still be the ProgramData
        # file, so the error message can name the file to create.
        _local, installed = isolated_roots

        path, source = resolve_env_path()

        assert path == installed
        assert "installed" in source
        assert path == installed_config_path()

    def test_a_source_checkout_uses_the_dot_env_next_to_the_scripts(self, isolated_roots):
        # This is what keeps the Phase 1 probe in C:\CoreOps-EasyTime-Probe
        # working after the connector is installed: it has its own .env.
        local, installed = isolated_roots
        local.write_text(EASYTIME_BLOCK + COREOPS_BLOCK, encoding="utf-8")
        installed.parent.mkdir(parents=True, exist_ok=True)
        installed.write_text(
            EASYTIME_BLOCK + COREOPS_BLOCK.replace("admin-pc-01", "installed-pc"),
            encoding="utf-8",
        )

        path, source = resolve_env_path()

        assert path == local
        assert "checkout" in source

    def test_the_override_variable_wins_over_both(self, isolated_roots, tmp_path, monkeypatch):
        local, installed = isolated_roots
        local.write_text(EASYTIME_BLOCK + COREOPS_BLOCK, encoding="utf-8")
        installed.parent.mkdir(parents=True, exist_ok=True)
        installed.write_text(EASYTIME_BLOCK + COREOPS_BLOCK, encoding="utf-8")
        chosen = write_env(
            tmp_path, EASYTIME_BLOCK + COREOPS_BLOCK.replace("admin-pc-01", "override-pc")
        )
        monkeypatch.setenv(ENV_FILE_OVERRIDE_VAR, str(chosen))

        path, source = resolve_env_path()

        assert path == chosen
        assert ENV_FILE_OVERRIDE_VAR in source
        assert load_connector_config().coreops.connector_id == "override-pc"

    def test_an_explicit_argument_wins_over_the_override_variable(
        self, isolated_roots, tmp_path, monkeypatch
    ):
        monkeypatch.setenv(ENV_FILE_OVERRIDE_VAR, str(tmp_path / "ignored.env"))
        argument = write_env(tmp_path, EASYTIME_BLOCK + COREOPS_BLOCK)

        path, source = resolve_env_path(argument)

        assert path == argument
        assert source == "explicit path"

    def test_resolution_does_not_depend_on_the_current_directory(
        self, isolated_roots, tmp_path, monkeypatch
    ):
        # The scheduled task runs with whatever working directory Windows feels
        # like giving it. The answer must not move.
        _local, installed = isolated_roots
        installed.parent.mkdir(parents=True, exist_ok=True)
        installed.write_text(EASYTIME_BLOCK + COREOPS_BLOCK, encoding="utf-8")
        elsewhere = tmp_path / "some" / "other" / "cwd"
        elsewhere.mkdir(parents=True)

        before = resolve_env_path()
        original = os.getcwd()
        try:
            os.chdir(elsewhere)
            after = resolve_env_path()
            loaded = load_connector_config()
        finally:
            os.chdir(original)

        assert after == before
        assert after[0].is_absolute()
        assert loaded.coreops.connector_id == "admin-pc-01"

    def test_local_and_installed_paths_are_not_the_same_file(self, isolated_roots):
        local, installed = isolated_roots
        assert local != installed


class TestDataRootOverride:
    """``run_sync.ps1 -DataRoot`` must move config, data AND logs together.

    If the wrapper and the Python process resolved the mutable root separately
    they could report two different state files, which is exactly the ambiguity
    the installed layout exists to remove.
    """

    def test_it_moves_the_config_data_and_log_roots_together(
        self, isolated_roots, tmp_path, monkeypatch
    ):
        elsewhere = tmp_path / "relocated"
        (elsewhere / "config").mkdir(parents=True)
        (elsewhere / "config" / INSTALLED_CONFIG_FILENAME).write_text(
            EASYTIME_BLOCK + COREOPS_BLOCK, encoding="utf-8"
        )
        monkeypatch.setenv(DATA_ROOT_OVERRIDE_VAR, str(elsewhere))

        path, _source = resolve_env_path()
        config = load_connector_config()

        assert path == elsewhere / "config" / INSTALLED_CONFIG_FILENAME
        assert config.sync.state_path == elsewhere / "data" / "state.db"
        assert config.sync.lock_path == elsewhere / "data" / "sync.lock"
        assert config.sync.log_dir == elsewhere / "logs"

    def test_an_explicit_path_setting_still_beats_the_data_root(
        self, isolated_roots, tmp_path, monkeypatch
    ):
        # The override sets the DEFAULT root. SYNC_STATE_PATH is the admin's
        # explicit choice and must not be silently overruled by a wrapper flag.
        elsewhere = tmp_path / "relocated"
        (elsewhere / "config").mkdir(parents=True)
        (elsewhere / "config" / INSTALLED_CONFIG_FILENAME).write_text(
            EASYTIME_BLOCK + COREOPS_BLOCK + f"SYNC_STATE_PATH={tmp_path / 'pinned.db'}\n",
            encoding="utf-8",
        )
        monkeypatch.setenv(DATA_ROOT_OVERRIDE_VAR, str(elsewhere))

        sync = load_connector_config().sync

        assert sync.state_path == tmp_path / "pinned.db"
        assert sync.lock_path == tmp_path / "sync.lock"  # follows the state file
        assert sync.log_dir == elsewhere / "logs"  # unpinned, so it follows the root


class TestMissingConfigErrors:
    def test_the_error_names_the_installed_file_and_how_to_create_it(self, isolated_roots):
        _local, installed = isolated_roots

        with pytest.raises(EasyTimeConfigError) as exc:
            load_config()

        message = str(exc.value)
        assert str(installed) in message
        assert "connector.env.example" in message
        assert "notepad" in message

    def test_an_override_pointing_at_a_missing_file_fails_even_in_read_only_mode(
        self, isolated_roots, tmp_path, monkeypatch
    ):
        # An override that names a file which is not there is a typo, not a
        # half-finished install. --status must not quietly read nothing.
        missing = tmp_path / "typo.env"
        monkeypatch.setenv(ENV_FILE_OVERRIDE_VAR, str(missing))

        with pytest.raises(EasyTimeConfigError) as exc:
            load_config(require_credentials=False)

        assert str(missing) in str(exc.value)
        assert ENV_FILE_OVERRIDE_VAR in str(exc.value)

    def test_a_half_finished_install_still_answers_status(self, isolated_roots):
        # No file at all, read-only mode: tolerated, so --status can report what
        # is wrong instead of refusing to start.
        config = load_connector_config(require_credentials=False)

        assert config.coreops.connector_token == ""

    def test_no_configured_secret_can_reach_the_error_message(
        self, isolated_roots, tmp_path, monkeypatch
    ):
        # The path in the message is attacker-chosen only in the sense that an
        # admin could park a secret in a FILENAME. Assert the message carries
        # nothing read from inside any file, by putting secrets in the ambient
        # environment and checking they do not surface.
        monkeypatch.setenv("EASYTIME_PASSWORD", "hunter2-should-never-appear")
        monkeypatch.setenv("COREOPS_CONNECTOR_TOKEN", "token-should-never-appear")

        with pytest.raises(EasyTimeConfigError) as exc:
            load_config()

        message = str(exc.value)
        assert "hunter2-should-never-appear" not in message
        assert "token-should-never-appear" not in message
