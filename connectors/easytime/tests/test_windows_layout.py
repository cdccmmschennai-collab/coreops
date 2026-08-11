"""Static verification of the Windows installation contract.

These tests read the PowerShell scripts as text. They cannot prove the scripts
run correctly on a Windows admin PC - only a real install can do that - but they
do pin the decisions that are easy to undo by accident and expensive to discover
on site:

    * the application is COPIED into Program Files, not merely referenced
    * the mutable roots are under ProgramData
    * the Phase 1 probe directory is never an installation destination
    * nothing deletes a configuration file or a state database
    * scheduled-task registration stays opt-in
    * the package whitelist ships every file the installer needs, and no secret

Parsing PowerShell with regular expressions is normally a bad idea. It is
acceptable here because the only constructs read are simple single-quoted array
literals and param defaults that this repository owns and controls.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

CONNECTOR_DIR = Path(__file__).resolve().parents[1]

APP_ROOT = r"C:\Program Files\CoreOps\EasyTimeConnector"
DATA_ROOT = r"C:\ProgramData\CoreOps\EasyTimeConnector"
PROBE_ROOT = r"C:\CoreOps-EasyTime-Probe"

INSTALLER = CONNECTOR_DIR / "install_connector.ps1"
RUN_SYNC = CONNECTOR_DIR / "run_sync.ps1"
SETUP_CONNECTOR = CONNECTOR_DIR / "setup_connector.ps1"
SETUP_PROBE = CONNECTOR_DIR / "setup_probe.ps1"
PACKAGER = CONNECTOR_DIR / "package_connector.ps1"

# Everything an installed connector needs in order to run one sync. Derived from
# the imports of sync.py plus the entry-point scripts, not from the whitelist
# itself - otherwise the test would only prove the whitelist equals itself.
REQUIRED_RUNTIME_FILES = {
    "config.py",
    "exceptions.py",
    "schemas.py",
    "client.py",
    "redaction.py",
    "coreops_client.py",
    "mapper.py",
    "state.py",
    "runlock.py",
    "logging_setup.py",
    "exit_codes.py",
    "sync_service.py",
    "sync.py",
    "requirements.txt",
    ".env.example",
    "README.md",
    "install_connector.ps1",
    "setup_connector.ps1",
    "run_sync.ps1",
}

# Never shipped, never installed, never written by an installer.
FORBIDDEN_IN_PACKAGE = {
    ".env",
    "connector.env",
    "state.db",
    ".venv",
    "dist",
    "tests",
    "__pycache__",
    ".pytest_cache",
}


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def ps_code(source: str) -> str:
    """The script with its comment-based help and line comments removed.

    A comment is allowed to *name* something the code must not do - that is
    what the comments in these scripts are for - so "does the code do X?" has
    to be asked of the code alone.
    """
    without_help = re.sub(r"<#.*?#>", "", source, flags=re.DOTALL)
    return "\n".join(
        re.sub(r"#.*$", "", line)
        for line in without_help.splitlines()
        if not line.lstrip().startswith("#")
    )


def ps_string_array(source: str, name: str) -> list[str]:
    """Extract the single-quoted entries of a ``$Name = @( ... )`` literal."""
    match = re.search(rf"\${name}\s*=\s*@\((.*?)\n\)", source, re.DOTALL)
    assert match, f"${name} array literal not found"
    return re.findall(r"'([^']+)'", match.group(1))


@pytest.fixture(scope="module")
def installer() -> str:
    return read(INSTALLER)


@pytest.fixture(scope="module")
def packager() -> str:
    return read(PACKAGER)


@pytest.fixture(scope="module")
def run_sync() -> str:
    return read(RUN_SYNC)


class TestInstallerRoots:
    def test_program_files_is_the_default_application_root(self, installer):
        assert re.search(
            rf"\$InstallRoot\s*=\s*'{re.escape(APP_ROOT)}'", installer
        ), "the default -InstallRoot must be the approved Program Files path"

    def test_programdata_is_the_default_mutable_root(self, installer):
        assert re.search(
            rf"\$DataRoot\s*=\s*'{re.escape(DATA_ROOT)}'", installer
        ), "the default -DataRoot must be the approved ProgramData path"

    @pytest.mark.parametrize("subdir", ["config", "data", "logs"])
    def test_each_programdata_subdirectory_is_created(self, installer, subdir):
        assert f"Join-Path $DataRoot '{subdir}'" in installer
        assert "New-DirectoryIfMissing $" in installer

    def test_every_final_path_is_printed(self, installer):
        # The operator must be able to read the layout off the console rather
        # than infer it. One line per thing that has a location.
        for label in (
            "Application   :",
            "Virtualenv    :",
            "Config file   :",
            "State         :",
            "Lock          :",
            "Connector logs:",
        ):
            assert label in installer, f"the summary does not print {label!r}"


class TestInstallerCopiesTheApplication:
    def test_an_explicit_whitelist_drives_the_copy(self, installer):
        files = ps_string_array(installer, "AppFiles")

        assert "sync.py" in files
        assert "run_sync.ps1" in files
        assert "setup_connector.ps1" in files

    def test_the_whitelist_carries_no_secret_or_generated_file(self, installer):
        files = set(ps_string_array(installer, "AppFiles"))

        assert not (files & FORBIDDEN_IN_PACKAGE), (
            "the installer whitelist names a file that must never be copied"
        )
        assert not [name for name in files if name.endswith((".db", ".lock", ".log"))]

    def test_files_are_actually_copied_into_the_install_root(self, installer):
        assert re.search(
            r"Copy-Item\s+-LiteralPath\s+\$from\s+-Destination\s+\$to", installer
        ), "install_connector.ps1 must copy the whitelisted files, not just create folders"
        assert "$to   = Join-Path $InstallRoot $name" in installer

    def test_the_runtime_whitelist_covers_everything_sync_needs(self, installer):
        files = set(ps_string_array(installer, "AppFiles"))

        missing = REQUIRED_RUNTIME_FILES - files
        assert not missing, f"the installer would not copy: {sorted(missing)}"

    def test_every_whitelisted_file_exists_in_the_repository(self, installer):
        for name in ps_string_array(installer, "AppFiles"):
            assert (CONNECTOR_DIR / name).is_file(), f"{name} is whitelisted but absent"


class TestInstallerNeverTouchesTheProbe:
    def test_the_probe_root_is_not_an_installation_destination(self, installer):
        # It appears only as the guard constant and in the refusal message.
        assert f"$ProbeRoot = '{PROBE_ROOT}'" in installer
        assert "Test-IsUnder $pair.Path $ProbeRoot" in installer

    def test_nothing_is_written_or_removed_under_the_probe_root(self, installer):
        for line in installer.splitlines():
            if "$ProbeRoot" not in line:
                continue
            for verb in ("Copy-Item", "New-Item", "Remove-Item", "Set-Content", "Out-File"):
                assert verb not in line, f"{verb} applied to the probe root: {line.strip()}"

    def test_the_probe_setup_script_is_preserved(self, installer):
        # Backward compatibility: the Phase 1 workflow keeps working.
        assert "setup_probe.ps1" in ps_string_array(installer, "AppFiles")
        assert SETUP_PROBE.is_file()


class TestInstallerIsSafeToRerun:
    def test_it_never_deletes_a_directory_tree(self, installer):
        assert "-Recurse" not in installer, (
            "an installer that recursively deletes is an installer that loses a cursor"
        )

    def test_it_refuses_rather_than_deletes_a_shadowing_env_file(self, installer):
        assert "NOT deleted automatically" in installer
        assert "$StrayInstalled = Join-Path $InstallRoot '.env'" in installer

    def test_an_existing_config_file_is_left_alone(self, installer):
        assert "left exactly as it was" in installer
        # The only thing copied into the config directory is the example.
        config_copies = [
            line
            for line in installer.splitlines()
            if "Copy-Item" in line and "Destination $" in line
        ]
        assert any("$ExampleFile" in line for line in config_copies)
        assert not any("Destination $ConfigFile" in line for line in config_copies)

    def test_it_does_not_write_credentials(self, installer):
        assert "No installer writes a credential for you" in installer
        assert "EASYTIME_PASSWORD=" not in installer
        assert "COREOPS_CONNECTOR_TOKEN=" not in installer


class TestScheduledTasksAreOptIn:
    def test_the_switch_defaults_to_off(self, installer):
        assert "[switch]$CreateScheduledTask" in installer

    def test_registration_is_guarded_by_the_switch(self, installer):
        guard = installer.index("if (-not $CreateScheduledTask)")
        first_register = installer.index("Register-ScheduledTask")
        assert guard < first_register, (
            "Register-ScheduledTask must sit inside the opt-in branch"
        )

    def test_the_default_run_says_it_created_nothing(self, installer):
        assert "not created (pass -CreateScheduledTask to register them)" in installer

    def test_no_other_script_registers_a_task(self, run_sync):
        for path in (RUN_SYNC, SETUP_CONNECTOR, SETUP_PROBE, PACKAGER):
            assert "Register-ScheduledTask" not in read(path), (
                f"{path.name} must not create a scheduled task"
            )


class TestRunSyncIsLocationIndependent:
    def test_it_derives_every_path_from_the_script_location(self, run_sync):
        assert "$AppRoot    = $PSScriptRoot" in run_sync
        # $PWD / Get-Location would make the answer depend on the caller.
        code = ps_code(run_sync)
        assert "$PWD" not in code
        assert "Get-Location" not in code
        # Every path the script builds hangs off $AppRoot or an absolute root.
        for variable in ("$SyncFile", "$VenvPython", "$PackagedExe", "$LocalEnv"):
            assert re.search(
                rf"{re.escape(variable)}\s*=\s*Join-Path \$AppRoot", code
            ), f"{variable} is not derived from $AppRoot"

    def test_the_child_process_working_directory_is_pinned(self, run_sync):
        assert "WorkingDirectory       = $AppRoot" in run_sync

    def test_it_resolves_the_installed_configuration_file(self, run_sync):
        assert "Join-Path $ConfigDir 'connector.env'" in run_sync
        assert "$env:COREOPS_CONNECTOR_ENV_FILE = $ResolvedEnv" in run_sync

    def test_the_child_process_cannot_resolve_a_different_data_root(self, run_sync):
        # Otherwise the wrapper reports one state file and sync.py uses another.
        assert "$env:COREOPS_CONNECTOR_DATA_ROOT = $DataRoot" in run_sync

    def test_the_wrapper_log_does_not_land_under_program_files(self, run_sync):
        # $AppRoot\logs is the development fallback only; ProgramData is tried
        # first, and TEMP is the last resort.
        assert "$candidates += $ProgramDataLogDir" in run_sync
        assert "GetTempPath()" in run_sync

    def test_it_propagates_the_python_exit_code(self, run_sync):
        assert "$exitCode = $process.ExitCode" in run_sync
        assert run_sync.rstrip().endswith("exit $exitCode")

    def test_it_still_redacts_captured_output(self, run_sync):
        assert "$SensitivePatterns" in run_sync
        assert "Protect-Text $stdout" in run_sync
        assert "Protect-Text $stderr" in run_sync

    def test_no_credential_can_be_passed_as_a_parameter(self, run_sync):
        params = run_sync[: run_sync.index("$ErrorActionPreference")]
        for forbidden in ("Password", "Token", "Secret", "Credential", "ApiKey"):
            assert f"${forbidden}" not in params, (
                f"-{forbidden} must not be a run_sync.ps1 parameter"
            )

    def test_the_supported_modes_are_unchanged(self, run_sync):
        match = re.search(r"\[ValidateSet\(([^)]*)\)\]", run_sync)
        assert match
        modes = re.findall(r"'([^']+)'", match.group(1))
        assert modes == [
            "Incremental",
            "Reconcile",
            "Backfill",
            "Status",
            "CheckConfig",
        ]


class TestParameterBlocksBind:
    """A script that will not bind its parameters cannot be run at all.

    ``[Parameter()]`` or ``[CmdletBinding()]`` makes a script ADVANCED, and
    PowerShell then adds the common parameters itself. Re-declaring one is not a
    duplicate flag, it is a hard binding error - "A parameter with the name
    'Verbose' was defined multiple times" - and every mode of the script fails
    before a single line of the body runs. That is exactly the kind of defect
    that survives a green Python test suite and surfaces on the admin PC.
    """

    # PowerShell adds all of these to any advanced script or function.
    COMMON_PARAMETERS = {
        "Verbose",
        "Debug",
        "ErrorAction",
        "ErrorVariable",
        "WarningAction",
        "WarningVariable",
        "InformationAction",
        "InformationVariable",
        "OutVariable",
        "OutBuffer",
        "PipelineVariable",
        "WhatIf",
        "Confirm",
    }

    SHIPPED_SCRIPTS = [
        INSTALLER,
        RUN_SYNC,
        SETUP_CONNECTOR,
        SETUP_PROBE,
        CONNECTOR_DIR / "run_probe.ps1",
        PACKAGER,
        CONNECTOR_DIR / "package_probe.ps1",
    ]

    @pytest.mark.parametrize("script", SHIPPED_SCRIPTS, ids=lambda p: p.name)
    def test_no_script_redeclares_a_common_parameter(self, script):
        source = ps_code(read(script))
        match = re.search(r"\nparam\s*\((.*?)\n\)", source, re.DOTALL)
        assert match, f"{script.name} has no param block"
        block = match.group(1)

        is_advanced = "[CmdletBinding()]" in source or "[Parameter(" in block
        declared = set(re.findall(r"\$(\w+)", block))
        clash = declared & self.COMMON_PARAMETERS

        if is_advanced:
            assert not clash, (
                f"{script.name} is an advanced script and re-declares "
                f"{sorted(clash)}; PowerShell refuses to bind it"
            )

    def test_run_sync_takes_verbose_from_the_common_parameter(self, run_sync):
        code = ps_code(run_sync)
        assert "[switch]$Verbose" not in code
        assert "$PSBoundParameters.ContainsKey('Verbose')" in code
        assert "--verbose" in code


class TestSetupConnector:
    def test_it_exists_and_is_the_documented_entry_point(self):
        assert SETUP_CONNECTOR.is_file()

    def test_it_creates_the_venv_in_the_installed_application_directory(self):
        source = read(SETUP_CONNECTOR)
        assert "if ([string]::IsNullOrWhiteSpace($AppRoot)) { $AppRoot = $PSScriptRoot }" in source
        assert "$VenvDir      = Join-Path $AppRoot '.venv'" in source

    def test_it_installs_only_the_pinned_requirements(self):
        source = read(SETUP_CONNECTOR)
        assert "-m pip install -r $Requirements" in source
        # No loose package names, and nothing installed outside the venv.
        assert not re.search(r"pip install (?!-r|--upgrade pip)", source)
        assert "$VenvPython -m pip" in source

    def test_it_prints_the_python_and_virtualenv_paths(self):
        source = read(SETUP_CONNECTOR)
        for label in ("Base Python   :", "Virtualenv    :", "Venv Python   :"):
            assert label in source

    def test_it_fails_clearly_when_python_is_unavailable(self):
        source = read(SETUP_CONNECTOR)
        assert "No usable Python" in source
        assert "python.org/downloads/windows" in source

    def test_it_stores_no_credential(self):
        source = read(SETUP_CONNECTOR)
        assert "never writes credentials" in source
        assert "EASYTIME_PASSWORD=" not in source
        assert "COREOPS_CONNECTOR_TOKEN=" not in source


class TestPackageContents:
    def test_the_whitelist_ships_every_required_runtime_file(self, packager):
        shipped = set(ps_string_array(packager, "Whitelist"))

        missing = REQUIRED_RUNTIME_FILES - shipped
        assert not missing, f"the package would not contain: {sorted(missing)}"

    def test_the_package_ships_everything_the_installer_copies(self, packager, installer):
        shipped = set(ps_string_array(packager, "Whitelist"))
        installed = set(ps_string_array(installer, "AppFiles"))

        assert not (installed - shipped), (
            "install_connector.ps1 would look for files the ZIP does not carry: "
            f"{sorted(installed - shipped)}"
        )

    def test_the_whitelist_names_nothing_forbidden(self, packager):
        shipped = set(ps_string_array(packager, "Whitelist"))

        assert not (shipped & FORBIDDEN_IN_PACKAGE)

    @pytest.mark.parametrize(
        "pattern",
        [
            r"(^|/)\.env$",
            r"(^|/)connector\.env$",
            r"(^|/)\.venv/",
            r"(^|/)logs/",
            r"(^|/)data/",
            r"(^|/)dist/",
            r"(^|/)tests/",
            r"(^|/)__pycache__/",
            r"(^|/)\.pytest_cache/",
            r"(^|/)\.git",
            r"\.db$",
            r"\.lock$",
            r"\.log$",
        ],
    )
    def test_the_post_build_verification_rejects_it(self, packager, pattern):
        forbidden = ps_string_array(packager, "ForbiddenEntryPatterns")

        assert pattern in forbidden, f"{pattern} is not checked after zipping"

    def test_the_archive_is_verified_entry_by_entry_after_building(self, packager):
        assert "ZipFile]::OpenRead" in packager
        assert "unexpected entries" in packager
        assert "expected entries are missing" in packager

    def test_the_secret_scan_is_still_in_place(self, packager):
        assert "(?i)(PASSWORD|PASSWD|TOKEN|SECRET|API_?KEY)" in packager
        assert "must never be shipped" in packager

    def test_the_build_scripts_do_not_ship_themselves(self, packager):
        shipped = set(ps_string_array(packager, "Whitelist"))

        assert "package_connector.ps1" not in shipped
        assert "package_probe.ps1" not in shipped


class TestDocumentedCommandsAreReal:
    """Every command in the README must match a real parameter declaration."""

    @pytest.fixture(scope="class")
    def readme(self) -> str:
        return read(CONNECTOR_DIR / "README.md")

    def test_the_readme_documents_the_installed_roots(self, readme):
        assert APP_ROOT in readme
        assert DATA_ROOT in readme
        assert r"config\connector.env" in readme or "connector.env" in readme

    def test_every_run_sync_switch_used_in_the_readme_is_declared(self, readme, run_sync):
        declared = set(re.findall(r"\[\w+\(?[^\]]*\)?\]\s*\n?\s*\$(\w+)", run_sync))
        declared |= set(re.findall(r"\[string\]\$(\w+)", run_sync))
        declared |= set(re.findall(r"\[switch\]\$(\w+)", run_sync))
        declared |= set(re.findall(r"\[int\]\$(\w+)", run_sync))

        used = set(re.findall(r"run_sync\.ps1[^\n`]*?-(\w+)", readme))

        assert used, "the README documents no run_sync.ps1 invocation"
        assert used <= declared, f"undeclared parameter(s) in the README: {sorted(used - declared)}"

    def test_the_readme_names_setup_connector_as_the_setup_step(self, readme):
        assert "setup_connector.ps1" in readme

    def test_the_readme_states_task_scheduler_is_not_activated(self, readme):
        assert "NOT activated" in readme or "not activated" in readme
