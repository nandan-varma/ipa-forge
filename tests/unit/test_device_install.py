"""Regression tests for preserving app data and reporting real launch failures."""

from __future__ import annotations

import importlib.machinery
import importlib.util
from pathlib import Path

import pytest


@pytest.fixture
def installer():
    script = Path(__file__).resolve().parents[2] / "scripts" / "device-install"
    loader = importlib.machinery.SourceFileLoader("device_install_tests", str(script))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def extension_error(module):
    return module.DevicectlError({}, "Info.plist missing at /App.app/PlugIns/Notification.appex/Info.plist")


def test_upgrade_failure_never_silently_uninstalls(installer, monkeypatch, tmp_path):
    calls = []

    def fail(*args, **kwargs):
        calls.append(args)
        raise extension_error(installer)

    monkeypatch.setattr(installer, "devicectl_json", fail)
    with pytest.raises(installer.Fail, match="installed app and data retained"):
        installer.install("phone", tmp_path / "app.ipa", "com.example.app")
    assert len(calls) == 1
    assert calls[0][:3] == ("device", "install", "app")


def test_failed_backup_prevents_uninstall(installer, monkeypatch, tmp_path):
    calls = []

    def fail(*args, **kwargs):
        calls.append(args)
        raise extension_error(installer)

    def backup(*args):
        raise OSError("disk full")

    monkeypatch.setattr(installer, "devicectl_json", fail)
    monkeypatch.setattr(installer, "backup_app_data", backup)
    with pytest.raises(installer.Fail, match="original app was not removed"):
        installer.install("phone", tmp_path / "app.ipa", "app", recovery=tmp_path / "backup")
    assert len(calls) == 1


def test_recovery_orders_backup_before_uninstall_and_restore_after_install(installer, monkeypatch, tmp_path):
    calls = []

    def call(*args, **kwargs):
        calls.append(args[:3])
        if len(calls) == 1:
            raise extension_error(installer)
        return {}

    monkeypatch.setattr(installer, "devicectl_json", call)
    monkeypatch.setattr(installer, "backup_app_data", lambda *args: calls.append("backup") or {"x": "hash"})
    monkeypatch.setattr(installer, "restore_app_data", lambda *args: calls.append("restore"))
    installer.install("phone", tmp_path / "app.ipa", "app", recovery=tmp_path / "backup")
    assert calls == [
        ("device", "install", "app"),
        "backup",
        ("device", "uninstall", "app"),
        ("device", "install", "app"),
        "restore",
    ]


def test_generic_install_error_does_not_trigger_recovery(installer, monkeypatch, tmp_path):
    calls = []

    def call(*args, **kwargs):
        calls.append(args)
        raise installer.DevicectlError({}, "MIInstallerErrorDomain error 35: some other failure")

    monkeypatch.setattr(installer, "devicectl_json", call)
    with pytest.raises(installer.Fail, match="install failed"):
        installer.install("phone", tmp_path / "app.ipa", "app", recovery=tmp_path / "backup")
    assert len(calls) == 1


def test_restore_verifies_bytes_and_retains_backup_on_mismatch(installer, monkeypatch, tmp_path):
    backup = tmp_path / "backup"
    (backup / "Documents").mkdir(parents=True)
    (backup / "Library").mkdir()
    (backup / "Documents" / "settings").write_text("keep me")
    manifest = installer.data_manifest(backup)

    def call(*args, **kwargs):
        if args[:3] == ("device", "copy", "from"):
            dest = Path(args[args.index("--destination") + 1])
            if dest.name == "Documents":
                (dest / "settings").write_text("corrupted")
        return {}

    monkeypatch.setattr(installer, "devicectl_json", call)
    monkeypatch.setattr(installer, "stop_app", lambda *args: None)
    with pytest.raises(installer.Fail, match="verification failed"):
        installer.restore_app_data("phone", "app", backup, manifest)
    assert (backup / "Documents" / "settings").read_text() == "keep me"


def test_smoke_timeout_leaves_app_running_and_checks_device_executable(installer, monkeypatch, tmp_path):
    import subprocess

    killed = []

    class Console:
        def __init__(self, cmd, **kwargs):
            assert "--json-output" not in cmd
            self.waited = False

        def wait(self, timeout):
            if not self.waited:
                self.waited = True
                raise subprocess.TimeoutExpired("devicectl", timeout)
            return -9

        def kill(self):
            killed.append("console")

        def terminate(self):
            pytest.fail("SIGTERM would be forwarded to Spotify")

    monkeypatch.setattr(installer.subprocess, "Popen", Console)
    monkeypatch.setattr(installer, "crash_logs", lambda *args: [])
    monkeypatch.setattr(
        installer, "device_apps", lambda *args: [{"bundleIdentifier": "app", "url": "file:///App.app/"}]
    )
    monkeypatch.setattr(
        installer,
        "devicectl_json",
        lambda *args: {"runningProcesses": [{"processIdentifier": 123, "executable": "file:///App.app/Spotify"}]},
    )
    assert installer.smoke_test("phone", "app", "Spotify", 1, tmp_path)
    assert killed == ["console"]


def test_crash_with_blocked_log_is_not_misreported_as_locked_phone(installer, monkeypatch, tmp_path):
    class Console:
        def __init__(self, cmd, stdout, **kwargs):
            stdout.write(
                "SpotifyMod: blocked ad request\nNSInternalInconsistencyException\nApp terminated due to signal 6.\n"
            )
            stdout.flush()

        def wait(self, timeout):
            return 1

    monkeypatch.setattr(installer.subprocess, "Popen", Console)
    monkeypatch.setattr(installer, "crash_logs", lambda *args: [])
    monkeypatch.setattr(installer.time, "sleep", lambda seconds: None)
    assert not installer.smoke_test("phone", "app", "Spotify", 1, tmp_path)
