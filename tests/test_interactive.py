"""Unit coverage for dependency-free interactive helpers and CLI guardrails."""

import errno
import fcntl
import json
import os
import pty
import select
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import termios
import time
import unittest
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import interactive

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "jackett-search"

CLI_LOADER = SourceFileLoader("jackett_search_cli", str(SCRIPT))
CLI_SPEC = spec_from_loader(CLI_LOADER.name, CLI_LOADER)
assert CLI_SPEC is not None
cli = module_from_spec(CLI_SPEC)
CLI_LOADER.exec_module(cli)


class InstallationTests(unittest.TestCase):
    """Prove the Makefile installs runtime files independently of the checkout."""

    def test_default_install_locations_are_user_local(self):
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")

        self.assertIn("INSTALL_PREFIX ?= $(HOME)/.local", makefile)
        self.assertIn("INSTALL_DIR ?= $(INSTALL_PREFIX)/bin", makefile)
        self.assertIn("INSTALL_LIB_DIR ?= $(INSTALL_PREFIX)/lib/jackett-search", makefile)

    def test_docker_installation_uses_shared_network_and_service_dns(self):
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")

        self.assertIn("DOCKER_NETWORK := jackett-search", makefile)
        self.assertIn("ensure-jackett-network", makefile)
        self.assertIn("DOCKER_NETWORK_SETUP_CMD", makefile)
        self.assertIn("FLARESOLVERR_MANUAL_START_CMD", makefile)
        self.assertIn("JACKETT_MANUAL_START_CMD", makefile)
        self.assertIn("http://flaresolverr:8191", makefile)
        self.assertNotIn("host.docker.internal", makefile)
        self.assertNotIn("$(MAKE) --no-print-directory ensure-jackett-network", makefile)
        self.assertIn("COPYFILE_DISABLE=1 cp -R", makefile)
        self.assertIn("-name '._*'", makefile)

        for compose_name in ("jackett-compose.yml", "flaresolverr-compose.yml"):
            compose = (ROOT / compose_name).read_text(encoding="utf-8")
            self.assertIn("networks:\n      - jackett-search", compose)
            self.assertIn("jackett-search:\n    external: true", compose)

    def test_make_dry_runs_do_not_execute_docker_or_write_config(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_path = Path(temporary_directory)
            fake_bin = temporary_path / "bin"
            fake_bin.mkdir()
            docker_log = temporary_path / "docker.log"
            fake_docker = fake_bin / "docker"
            fake_docker.write_text(
                '#!/bin/sh\nprintf \'%s\\n\' "$*" >> "$DOCKER_LOG"\nexit 0\n',
                encoding="utf-8",
            )
            fake_docker.chmod(0o755)

            environment = os.environ | {
                "DOCKER_LOG": str(docker_log),
                "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
            }
            for target in (
                "install",
                "install-flaresolverr",
                "install-jackett",
                "up-flaresolverr",
                "up-jackett",
                "up",
            ):
                config_dir = temporary_path / target / "config"
                dry_run = subprocess.run(
                    [
                        "make",
                        "--no-print-directory",
                        "-n",
                        target,
                        f"CONFIG_DIR={config_dir}",
                        f"JACKETT_NATIVE_CONFIG_DIR={temporary_path / 'native'}",
                    ],
                    cwd=ROOT,
                    capture_output=True,
                    check=False,
                    env=environment,
                    text=True,
                )

                self.assertEqual(0, dry_run.returncode, dry_run.stderr)
                self.assertFalse(config_dir.exists(), target)

            self.assertFalse(docker_log.exists())

            network_setup = subprocess.run(
                ["make", "--no-print-directory", "ensure-jackett-network"],
                cwd=ROOT,
                capture_output=True,
                check=False,
                env=environment,
                text=True,
            )
            self.assertEqual(0, network_setup.returncode, network_setup.stderr)
            self.assertIn("network inspect jackett-search", docker_log.read_text(encoding="utf-8"))

    def test_make_install_creates_a_standalone_runtime(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            install_root = Path(temporary_directory)
            install_dir = install_root / "bin"
            install_lib_dir = install_root / "lib" / "jackett-search"
            config_dir = install_root / "config"
            install_arguments = [
                "make",
                "--no-print-directory",
                "install",
                f"INSTALL_DIR={install_dir}",
                f"INSTALL_LIB_DIR={install_lib_dir}",
                f"CONFIG_DIR={config_dir}",
            ]
            installed = subprocess.run(
                install_arguments,
                cwd=ROOT,
                capture_output=True,
                check=False,
                text=True,
            )

            self.assertEqual(0, installed.returncode, installed.stderr)
            launcher = install_dir / "jackett-search"
            self.assertTrue(launcher.is_symlink())
            self.assertEqual((install_lib_dir / "jackett-search").resolve(), launcher.resolve())
            self.assertTrue((install_lib_dir / "interactive.py").is_file())
            self.assertNotEqual(SCRIPT.resolve(), launcher.resolve())
            version = subprocess.run(
                [str(launcher), "--version"],
                capture_output=True,
                check=False,
                text=True,
            )
            self.assertEqual(0, version.returncode, version.stderr)
            self.assertIn("jackett-search 0.3.0", version.stdout)

            uninstalled = subprocess.run(
                [
                    "make",
                    "--no-print-directory",
                    "uninstall",
                    f"INSTALL_DIR={install_dir}",
                    f"INSTALL_LIB_DIR={install_lib_dir}",
                ],
                cwd=ROOT,
                capture_output=True,
                check=False,
                text=True,
            )
            self.assertEqual(0, uninstalled.returncode, uninstalled.stderr)
            self.assertFalse(launcher.exists())
            self.assertFalse(install_lib_dir.exists())

    def test_failed_standalone_upgrade_keeps_the_previous_runtime(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            install_root = Path(temporary_directory)
            install_dir = install_root / "bin"
            install_lib_dir = install_root / "lib" / "jackett-search"
            config_dir = install_root / "config"
            install_arguments = [
                "make",
                "--no-print-directory",
                "install",
                f"INSTALL_DIR={install_dir}",
                f"INSTALL_LIB_DIR={install_lib_dir}",
                f"CONFIG_DIR={config_dir}",
            ]
            initial_install = subprocess.run(
                install_arguments,
                cwd=ROOT,
                capture_output=True,
                check=False,
                text=True,
            )
            self.assertEqual(0, initial_install.returncode, initial_install.stderr)

            launcher = install_dir / "jackett-search"
            previous_script = (install_lib_dir / "jackett-search").read_bytes()
            previous_interactive = (install_lib_dir / "interactive.py").read_bytes()
            fake_bin = install_root / "fake-bin"
            fake_bin.mkdir()
            install_counter = install_root / "install-count"
            fake_install = fake_bin / "install"
            fake_install.write_text(
                "#!/bin/sh\n"
                "count=0\n"
                'if [ -f "$INSTALL_COUNTER" ]; then count=$(cat "$INSTALL_COUNTER"); fi\n'
                "count=$((count + 1))\n"
                'printf \'%s\\n\' "$count" > "$INSTALL_COUNTER"\n'
                'if [ "$count" -eq 2 ]; then exit 1; fi\n'
                'exec "$REAL_INSTALL" "$@"\n',
                encoding="utf-8",
            )
            fake_install.chmod(0o755)
            real_install = shutil.which("install")
            self.assertIsNotNone(real_install)
            environment = os.environ | {
                "INSTALL_COUNTER": str(install_counter),
                "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
                "REAL_INSTALL": str(real_install),
            }

            failed_upgrade = subprocess.run(
                install_arguments,
                cwd=ROOT,
                capture_output=True,
                check=False,
                env=environment,
                text=True,
            )

            self.assertNotEqual(0, failed_upgrade.returncode)
            self.assertIn("Cannot install", failed_upgrade.stdout)
            self.assertEqual(previous_script, (install_lib_dir / "jackett-search").read_bytes())
            self.assertEqual(
                previous_interactive,
                (install_lib_dir / "interactive.py").read_bytes(),
            )
            self.assertEqual((install_lib_dir / "jackett-search").resolve(), launcher.resolve())


class SearchParamsTests(unittest.TestCase):
    """Validate persisted search settings and history semantics."""

    def test_history_round_trip_deduplicates_and_uses_restrictive_permissions(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            history_path = Path(temporary_directory) / "history.json"
            dune = interactive.SearchParams("Dune", "seeders", 20, 10, "magnets")
            blade_runner = interactive.SearchParams("Blade Runner", "dlf,seeders", None, 30)
            history = interactive.record_history([dune], blade_runner, 50)
            history = interactive.record_history(history, dune, 50)

            interactive.save_history(history_path, history, 50)

            self.assertEqual([dune, blade_runner], interactive.load_history(history_path))
            self.assertEqual(0o600, history_path.stat().st_mode & 0o777)

    def test_invalid_history_entries_are_ignored(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            history_path = Path(temporary_directory) / "history.json"
            history_path.write_text(
                json.dumps([{"query": "valid"}, {"query": 42}, "not-a-dict"]),
                encoding="utf-8",
            )

            self.assertEqual(
                [interactive.SearchParams("valid")],
                interactive.load_history(history_path),
            )

    def test_clear_history_reports_whether_a_file_existed(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            history_path = Path(temporary_directory) / "history.json"
            self.assertFalse(interactive.clear_history(history_path))
            history_path.write_text("[]\n", encoding="utf-8")
            self.assertTrue(interactive.clear_history(history_path))
            self.assertFalse(history_path.exists())

    def test_form_selectors_and_numeric_fields_are_constrained(self):
        self.assertEqual(
            "seeders:asc", interactive.cycle_option(interactive.SORT_OPTIONS, "seeders", 1)
        )
        self.assertEqual(
            "seeders", interactive.cycle_option(interactive.SORT_OPTIONS, "dlf,seeders", 1)
        )
        self.assertEqual(
            "title:desc", interactive.cycle_option(interactive.SORT_OPTIONS, "dlf,seeders", -1)
        )
        self.assertEqual(
            "both", interactive.cycle_option(interactive.FILTER_OPTIONS, "torrents", 1)
        )
        self.assertFalse(interactive.accepts_field_character("Limit", "x"))
        self.assertTrue(interactive.accepts_field_character("Limit", "5"))
        self.assertTrue(interactive.accepts_field_character("Query", "x"))
        self.assertEqual("1", interactive.adjust_numeric_value("", 1))
        self.assertEqual("", interactive.adjust_numeric_value("", -1))
        self.assertEqual("0", interactive.adjust_numeric_value("0", -1))
        self.assertEqual("11", interactive.adjust_numeric_value("10", 1))
        with self.assertRaises(ValueError):
            interactive.adjust_numeric_value("10", 2)


class ConfigTests(unittest.TestCase):
    """Validate interactive preferences without parsing or exposing API secrets."""

    def test_preferences_and_updates_are_scoped_to_interactive_sections(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_path = Path(temporary_directory) / "config.toml"
            config_path.write_text(
                'url = "http://127.0.0.1:9117"\n'
                'api_key = "test-key"\n\n'
                "[interactive]\n"
                "persist_query_history = false\n"
                "history_limit = 12\n\n"
                "[interactive.clients.putio]\n"
                "last_folder_id = 123\n",
                encoding="utf-8",
            )
            os.chmod(config_path, 0o600)

            preferences = interactive.load_interactive_preferences(config_path)
            self.assertFalse(preferences.persist_query_history)
            self.assertEqual(12, preferences.history_limit)
            self.assertEqual(123, preferences.putio_last_folder_id)

            interactive.update_toml_sections(
                config_path,
                {
                    "interactive": {"last_client": "putio"},
                    "interactive.clients.putio": {"last_folder_id": 456},
                },
            )

            updated = config_path.read_text(encoding="utf-8")
            self.assertIn('api_key = "test-key"', updated)
            self.assertIn('last_client = "putio"', updated)
            self.assertIn("last_folder_id = 456", updated)
            self.assertEqual(0o600, config_path.stat().st_mode & 0o777)

    def test_history_uses_the_active_config_directory(self):
        config_path = Path("/tmp/example/jackett-search/config.toml")
        self.assertEqual(
            Path("/tmp/example/jackett-search/history.json"),
            interactive.history_path_for(config_path),
        )


class PutioTests(unittest.TestCase):
    """Validate put.io folder and command logic without contacting put.io."""

    def test_parse_folders_excludes_hidden_entries_and_builds_paths(self):
        payload = {
            "files": [
                {"id": 10, "name": "Movies", "file_type": "FOLDER", "is_hidden": False},
                {"id": 11, "name": "Internal", "file_type": "FOLDER", "is_hidden": True},
                {"id": 12, "name": "Movie.mkv", "file_type": "FILE", "is_hidden": False},
            ]
        }

        self.assertEqual(
            [interactive.PutioFolder(10, "Archive/Movies")],
            interactive.parse_putio_folders(payload, "Archive"),
        )

    def test_commands_are_argument_lists_not_shell_strings(self):
        url = "magnet:?xt=urn:btih:abc&dn=The Example"
        self.assertEqual(
            [
                "putio",
                "transfers",
                "add",
                "--url",
                url,
                "--save-parent-id",
                "42",
                "--output",
                "json",
            ],
            interactive.putio_add_command(url, 42),
        )
        self.assertEqual(
            ["putio", "transfers", "cancel", "--id", "99", "--output", "json"],
            interactive.putio_cancel_command(99),
        )

    def test_available_clients_only_reports_discoverable_commands(self):
        with mock.patch.object(interactive.sys, "platform", "darwin"), mock.patch.object(
            interactive.shutil,
            "which",
            side_effect=lambda command: "/usr/bin/" + command if command == "open" else None,
        ):
            self.assertEqual(
                [("default", "System default application")], interactive.available_clients()
            )

    def test_transfer_id_accepts_known_cli_response_shapes(self):
        self.assertEqual(99, interactive._transfer_id({"transfer": {"id": 99}}))
        self.assertEqual(100, interactive._transfer_id({"data": {"id": "100"}}))
        self.assertIsNone(interactive._transfer_id({"status": "OK"}))


class InteractiveStateTests(unittest.TestCase):
    """Keep the current-row state compatible with future batch selection."""

    def test_escape_cancels_an_in_progress_search(self):
        class FakeScreen:
            def getmaxyx(self):
                return 24, 100

            def erase(self):
                pass

            def addnstr(self, *_arguments):
                pass

            def refresh(self):
                pass

            def timeout(self, _delay):
                pass

            def getch(self):
                return 27

        fake_curses = SimpleNamespace(A_BOLD=0, A_DIM=0, error=RuntimeError)

        def slow_search(_params):
            time.sleep(5)
            return []

        with tempfile.TemporaryDirectory() as temporary_directory:
            config_path = Path(temporary_directory) / "config.toml"
            config_path.write_text('api_key = "test-key"\n', encoding="utf-8")
            session = interactive.InteractiveSession(
                interactive.SearchParams("Example"),
                slow_search,
                config_path,
            )
            session.screen = FakeScreen()
            session.curses = fake_curses
            session._confirm_search_transition = mock.Mock(return_value=True)

            started = time.monotonic()
            self.assertFalse(session._perform_search(record=True))

        self.assertLess(time.monotonic() - started, 1)
        self.assertEqual("Search cancelled.", session.status)
        session._confirm_search_transition.assert_called_once_with(
            "Cancel active search?",
            "This stops the current Jackett search and returns to its results.",
        )

    def test_ctrl_x_exits_an_in_progress_search_without_waiting_for_worker(self):
        class FakeScreen:
            def getmaxyx(self):
                return 24, 100

            def erase(self):
                pass

            def addnstr(self, *_arguments):
                pass

            def refresh(self):
                pass

            def timeout(self, _delay):
                pass

            def getch(self):
                return interactive.CTRL_X

        fake_curses = SimpleNamespace(A_BOLD=0, A_DIM=0, error=RuntimeError)

        def slow_search(_params):
            time.sleep(5)
            return []

        with tempfile.TemporaryDirectory() as temporary_directory:
            config_path = Path(temporary_directory) / "config.toml"
            config_path.write_text('api_key = "test-key"\n', encoding="utf-8")
            session = interactive.InteractiveSession(
                interactive.SearchParams("Example"),
                slow_search,
                config_path,
            )
            session.screen = FakeScreen()
            session.curses = fake_curses
            session._confirm_exit = mock.Mock(return_value=True)

            started = time.monotonic()
            with self.assertRaises(interactive.ExitInteractiveMode):
                session._perform_search(record=True)

        self.assertLess(time.monotonic() - started, 1)
        session._confirm_exit.assert_called_once_with()

    def test_ctrl_c_stops_an_in_progress_search_before_restoring_the_terminal(self):
        class FakeScreen:
            def getmaxyx(self):
                return 24, 100

            def erase(self):
                pass

            def addnstr(self, *_arguments):
                pass

            def refresh(self):
                pass

            def timeout(self, _delay):
                pass

            def getch(self):
                raise KeyboardInterrupt

        fake_curses = SimpleNamespace(A_BOLD=0, A_DIM=0, error=RuntimeError)

        def slow_search(_params):
            time.sleep(5)
            return []

        with tempfile.TemporaryDirectory() as temporary_directory:
            config_path = Path(temporary_directory) / "config.toml"
            config_path.write_text('api_key = "test-key"\n', encoding="utf-8")
            session = interactive.InteractiveSession(
                interactive.SearchParams("Example"),
                slow_search,
                config_path,
            )
            session.screen = FakeScreen()
            session.curses = fake_curses

            started = time.monotonic()
            with self.assertRaises(KeyboardInterrupt):
                session._perform_search(record=True)

        self.assertLess(time.monotonic() - started, 1)

    def test_escape_from_results_opens_the_search_form_without_exiting(self):
        class FakeScreen:
            def __init__(self):
                self.keys = iter((27, ord("q")))

            def keypad(self, _enabled):
                pass

            def timeout(self, _delay):
                pass

            def getch(self):
                return next(self.keys)

        fake_curses = SimpleNamespace(curs_set=mock.Mock(), error=RuntimeError)
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_path = Path(temporary_directory) / "config.toml"
            config_path.write_text('api_key = "test-key"\n', encoding="utf-8")
            session = interactive.InteractiveSession(
                interactive.SearchParams("Example"),
                lambda _params: [],
                config_path,
            )
            session.curses = fake_curses
            session._perform_search = mock.Mock()
            session._draw_results = mock.Mock()
            session._search_form = mock.Mock(return_value=False)
            session._confirm_search_transition = mock.Mock(return_value=True)

            session._run(FakeScreen())

        session._search_form.assert_called_once_with(allow_cancel=True)
        self.assertEqual(2, session._draw_results.call_count)
        session._confirm_search_transition.assert_called_once_with(
            "Leave current search?",
            "Return to the search form and keep this interactive session open.",
        )

    def test_ctrl_x_exits_from_results_after_confirmation(self):
        class FakeScreen:
            def __init__(self):
                self.keys = iter((interactive.CTRL_X,))

            def keypad(self, _enabled):
                pass

            def timeout(self, _delay):
                pass

            def getch(self):
                return next(self.keys)

        fake_curses = SimpleNamespace(curs_set=mock.Mock(), error=RuntimeError)
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_path = Path(temporary_directory) / "config.toml"
            config_path.write_text('api_key = "test-key"\n', encoding="utf-8")
            session = interactive.InteractiveSession(
                interactive.SearchParams("Example"),
                lambda _params: [],
                config_path,
            )
            session.curses = fake_curses
            session._perform_search = mock.Mock()
            session._draw_results = mock.Mock()
            session._confirm_exit = mock.Mock(return_value=True)

            with self.assertRaises(interactive.ExitInteractiveMode):
                session._run(FakeScreen())

        self.assertEqual(1, session._draw_results.call_count)
        session._confirm_exit.assert_called_once_with()

    def test_escape_from_results_keeps_results_when_transition_is_rejected(self):
        class FakeScreen:
            def __init__(self):
                self.keys = iter((27, ord("q")))

            def keypad(self, _enabled):
                pass

            def timeout(self, _delay):
                pass

            def getch(self):
                return next(self.keys)

        fake_curses = SimpleNamespace(curs_set=mock.Mock(), error=RuntimeError)
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_path = Path(temporary_directory) / "config.toml"
            config_path.write_text('api_key = "test-key"\n', encoding="utf-8")
            session = interactive.InteractiveSession(
                interactive.SearchParams("Example"),
                lambda _params: [],
                config_path,
            )
            session.curses = fake_curses
            session._perform_search = mock.Mock()
            session._draw_results = mock.Mock()
            session._search_form = mock.Mock()
            session._confirm_search_transition = mock.Mock(return_value=False)

            session._run(FakeScreen())

        session._search_form.assert_not_called()
        self.assertEqual(2, session._draw_results.call_count)

    def test_search_transition_confirmation_describes_escape_choices(self):
        class FakeScreen:
            def __init__(self):
                self.added = []

            def getmaxyx(self):
                return 24, 100

            def erase(self):
                pass

            def addnstr(self, _row, _column, text, *_arguments):
                self.added.append(text)

            def refresh(self):
                pass

            def timeout(self, _delay):
                pass

            def getch(self):
                return 27

        fake_curses = SimpleNamespace(A_BOLD=0, A_DIM=0, KEY_ENTER=343, error=RuntimeError)
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_path = Path(temporary_directory) / "config.toml"
            config_path.write_text('api_key = "test-key"\n', encoding="utf-8")
            session = interactive.InteractiveSession(
                interactive.SearchParams("Example"),
                lambda _params: [],
                config_path,
            )
            session.screen = FakeScreen()
            session.curses = fake_curses

            self.assertFalse(
                session._confirm_search_transition(
                    "Cancel active search?", "Stop the current Jackett search."
                )
            )

        self.assertIn("Cancel active search?", session.screen.added)
        self.assertIn("Enter/y confirm  Esc/n continue", session.screen.added)

    def test_q_remains_query_text_and_ctrl_x_exits_the_search_form(self):
        class FakeScreen:
            def __init__(self):
                self.added = []
                self.keys = iter((ord("q"), interactive.CTRL_X))

            def getmaxyx(self):
                return 24, 100

            def erase(self):
                pass

            def addnstr(self, _row, _column, text, *_arguments):
                self.added.append(text)

            def move(self, *_arguments):
                pass

            def refresh(self):
                pass

            def getch(self):
                return next(self.keys)

        fake_curses = SimpleNamespace(
            A_BOLD=0,
            A_DIM=0,
            KEY_BACKSPACE=263,
            KEY_BTAB=353,
            KEY_DOWN=258,
            KEY_END=360,
            KEY_ENTER=343,
            KEY_HOME=262,
            KEY_LEFT=260,
            KEY_RIGHT=261,
            KEY_UP=259,
            curs_set=mock.Mock(),
            error=RuntimeError,
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_path = Path(temporary_directory) / "config.toml"
            config_path.write_text('api_key = "test-key"\n', encoding="utf-8")
            session = interactive.InteractiveSession(
                interactive.SearchParams(),
                lambda _params: [],
                config_path,
            )
            session.screen = FakeScreen()
            session.curses = fake_curses
            session._confirm_exit = mock.Mock(return_value=True)

            with self.assertRaises(interactive.ExitInteractiveMode):
                session._search_form(allow_cancel=False)

        self.assertTrue(
            any("Query" in line and line.endswith(": q") for line in session.screen.added)
        )
        session._confirm_exit.assert_called_once_with()

    def test_numeric_form_fields_use_arrows_and_j_k_as_spinners(self):
        class FakeScreen:
            def __init__(self):
                self.added = []
                self.keys = iter(
                    (
                        9,
                        9,
                        259,
                        258,
                        9,
                        ord("k"),
                        ord("j"),
                        interactive.CTRL_X,
                    )
                )

            def getmaxyx(self):
                return 24, 100

            def erase(self):
                pass

            def addnstr(self, _row, _column, text, *_arguments):
                self.added.append(text)

            def move(self, *_arguments):
                pass

            def refresh(self):
                pass

            def getch(self):
                return next(self.keys)

        fake_curses = SimpleNamespace(
            A_BOLD=0,
            A_DIM=0,
            KEY_BACKSPACE=263,
            KEY_BTAB=353,
            KEY_DOWN=258,
            KEY_END=360,
            KEY_ENTER=343,
            KEY_HOME=262,
            KEY_LEFT=260,
            KEY_RIGHT=261,
            KEY_UP=259,
            curs_set=mock.Mock(),
            error=RuntimeError,
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_path = Path(temporary_directory) / "config.toml"
            config_path.write_text('api_key = "test-key"\n', encoding="utf-8")
            session = interactive.InteractiveSession(
                interactive.SearchParams(),
                lambda _params: [],
                config_path,
            )
            session.screen = FakeScreen()
            session.curses = fake_curses
            session._confirm_exit = mock.Mock(return_value=True)

            with self.assertRaises(interactive.ExitInteractiveMode):
                session._search_form(allow_cancel=False)

        self.assertTrue(
            any("Limit (results)" in line and line.endswith(": 1") for line in session.screen.added)
        )
        self.assertTrue(
            any("Limit (results)" in line and line.endswith(": 0") for line in session.screen.added)
        )
        self.assertTrue(
            any(
                "Timeout (seconds)" in line and line.endswith(": 11")
                for line in session.screen.added
            )
        )
        self.assertTrue(
            any(
                "Timeout (seconds)" in line and line.endswith(": 10")
                for line in session.screen.added
            )
        )

    def test_loading_panel_shows_completed_indexers_and_remaining_work(self):
        class FakeScreen:
            def __init__(self):
                self.added = []

            def getmaxyx(self):
                return 24, 100

            def erase(self):
                pass

            def addnstr(self, _row, _column, text, *_arguments):
                self.added.append(text)

            def refresh(self):
                pass

        fake_curses = SimpleNamespace(A_BOLD=0, A_DIM=0, error=RuntimeError)
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_path = Path(temporary_directory) / "config.toml"
            config_path.write_text('api_key = "test-key"\n', encoding="utf-8")
            session = interactive.InteractiveSession(
                interactive.SearchParams("Example"),
                lambda _params: [],
                config_path,
            )
            session.screen = FakeScreen()
            session.curses = fake_curses

            session._draw_loading("Searching for: Example", progress=(3, 5), spinner_index=1)

        self.assertIn("Indexers 3/5 (2 remaining)", session.screen.added)
        self.assertTrue(any(line.startswith("[") and "#" in line for line in session.screen.added))

    def test_search_worker_progress_is_rendered_in_the_parent_tui(self):
        class FakeScreen:
            def timeout(self, _delay):
                pass

            def getch(self):
                return -1

        fake_curses = SimpleNamespace(error=RuntimeError)

        def progressive_search(_params, report_progress):
            report_progress(0, 2)
            report_progress(1, 2)
            report_progress(2, 2)
            return []

        with tempfile.TemporaryDirectory() as temporary_directory:
            config_path = Path(temporary_directory) / "config.toml"
            config_path.write_text('api_key = "test-key"\n', encoding="utf-8")
            session = interactive.InteractiveSession(
                interactive.SearchParams("Example"),
                lambda _params: [],
                config_path,
                progress_search_callback=progressive_search,
            )
            session.screen = FakeScreen()
            session.curses = fake_curses
            session._draw_loading = mock.Mock()

            self.assertTrue(session._perform_search(record=True))

        self.assertIn(
            mock.call(
                "Searching for: Example",
                (1, 2),
                mock.ANY,
                "Discovering configured indexers",
            ),
            session._draw_loading.call_args_list,
        )
        self.assertEqual("Search complete: 0 result(s).", session.status)

    def test_escape_in_initial_search_form_does_not_return(self):
        class FakeScreen:
            def getmaxyx(self):
                return 24, 100

            def erase(self):
                pass

            def addnstr(self, *_arguments):
                pass

            def move(self, *_arguments):
                pass

            def refresh(self):
                pass

            def getch(self):
                if not hasattr(self, "escaped"):
                    self.escaped = True
                    return 27
                raise KeyboardInterrupt

        fake_curses = SimpleNamespace(A_BOLD=0, A_DIM=0, curs_set=mock.Mock(), error=RuntimeError)
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_path = Path(temporary_directory) / "config.toml"
            config_path.write_text('api_key = "test-key"\n', encoding="utf-8")
            session = interactive.InteractiveSession(
                interactive.SearchParams(),
                lambda _params: [],
                config_path,
            )
            session.screen = FakeScreen()
            session.curses = fake_curses

            with self.assertRaises(KeyboardInterrupt):
                session._search_form(allow_cancel=False)

        self.assertEqual(
            "Esc cancels dialogs. Press Ctrl-C to exit interactive mode.", session.status
        )

    def test_ctrl_c_exits_cleanly_after_curses_restores_the_terminal(self):
        fake_curses = SimpleNamespace(error=RuntimeError)
        fake_curses.wrapper = mock.Mock(side_effect=KeyboardInterrupt)
        terminal = SimpleNamespace(isatty=lambda: True)
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_path = Path(temporary_directory) / "config.toml"
            config_path.write_text('api_key = "test-key"\n', encoding="utf-8")
            session = interactive.InteractiveSession(
                interactive.SearchParams("Example"),
                lambda _params: [],
                config_path,
            )
            with mock.patch.object(interactive.sys, "stdin", terminal), mock.patch.object(
                interactive.sys, "stdout", terminal
            ), mock.patch.dict(sys.modules, {"curses": fake_curses}):
                session.run()

        fake_curses.wrapper.assert_called_once_with(session._run)

    def test_screen_writer_passes_length_before_curses_attributes(self):
        class FakeScreen:
            def __init__(self):
                self.calls = []

            def getmaxyx(self):
                return 24, 100

            def addnstr(self, *arguments):
                self.calls.append(arguments)

        class FakeCurses:
            error = Exception

        with tempfile.TemporaryDirectory() as temporary_directory:
            config_path = Path(temporary_directory) / "config.toml"
            config_path.write_text('api_key = "test-key"\n', encoding="utf-8")
            session = interactive.InteractiveSession(
                interactive.SearchParams("Example"),
                lambda _params: [],
                config_path,
            )
            session.screen = FakeScreen()
            session.curses = FakeCurses()
            session._add(2, 5, "Query", 42)

            self.assertEqual((2, 5, "Query", 94, 42), session.screen.calls[0])

    def test_actions_skip_unavailable_urls_and_keep_batch_marks_separate(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_path = Path(temporary_directory) / "config.toml"
            config_path.write_text('api_key = "test-key"\n', encoding="utf-8")
            session = interactive.InteractiveSession(
                interactive.SearchParams("Example"),
                lambda _params: [],
                config_path,
            )
            session.results = [
                {"Title": "magnet", "MagnetUri": "magnet:?xt=urn:btih:one"},
                {"Title": "torrent", "Link": "https://example.test/file.torrent"},
                {"Title": "metadata only"},
            ]

            self.assertEqual(["magnet"], session._available_actions())
            session.cursor_index = 1
            session._ensure_action_available()
            self.assertEqual("torrent", session.focused_action)
            self.assertEqual(["torrent"], session._available_actions())
            self.assertEqual(set(), session.marked_indices)

    def test_result_table_matches_standard_columns_and_shows_action_focus(self):
        class FakeScreen:
            def __init__(self):
                self.calls = []

            def getmaxyx(self):
                return 24, 180

            def erase(self):
                pass

            def addnstr(self, *arguments):
                self.calls.append(arguments)

            def refresh(self):
                pass

        fake_curses = SimpleNamespace(
            A_BOLD=1,
            A_DIM=2,
            A_REVERSE=4,
            A_UNDERLINE=8,
            curs_set=mock.Mock(),
            error=RuntimeError,
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_path = Path(temporary_directory) / "config.toml"
            config_path.write_text('api_key = "test-key"\n', encoding="utf-8")
            session = interactive.InteractiveSession(
                interactive.SearchParams("Example"),
                lambda _params: [],
                config_path,
            )
            session.screen = FakeScreen()
            session.curses = fake_curses
            session.colour_attributes = {"cyan": 16, "green": 32, "yellow": 64}
            session.results = [
                {
                    "Title": "Both URLs",
                    "Details": "https://example.test/details",
                    "Size": 1024,
                    "Seeders": 120,
                    "Peers": 4,
                    "Grabs": 2,
                    "DownloadVolumeFactor": 0.0,
                    "Tracker": "Example Tracker",
                    "MagnetUri": "magnet:?xt=urn:btih:one",
                    "Link": "https://example.test/file.torrent",
                },
                {
                    "Title": "Magnet only",
                    "MagnetUri": "magnet:?xt=urn:btih:two",
                },
            ]

            session._draw_results()

            rendered = [arguments[2] for arguments in session.screen.calls]
            self.assertIn("[M magnet] ", rendered)
            self.assertIn("T torrent   ", rendered)
            self.assertIn("T —         ", rendered)
            self.assertTrue(any("Title" in text and "Tracker" in text for text in rendered))
            self.assertTrue(
                any(text == f"{120:>{interactive.RESULT_SEEDS_WIDTH}}" for text in rendered)
            )

            session.screen.calls.clear()
            session._move_action(1)
            session._draw_results()

            rerendered = [arguments[2] for arguments in session.screen.calls]
            self.assertIn("M magnet   ", rerendered)
            self.assertIn("[T torrent] ", rerendered)
            self.assertEqual("torrent", session.focused_action)

    def test_cancelling_folder_discovery_restores_blocking_input(self):
        class FakeScreen:
            def __init__(self):
                self.timeouts = []

            def getmaxyx(self):
                return 24, 120

            def erase(self):
                pass

            def addnstr(self, *_args):
                pass

            def refresh(self):
                pass

            def timeout(self, value):
                self.timeouts.append(value)

            def getch(self):
                return 27

        class FakeCurses:
            A_BOLD = 0
            A_DIM = 0
            error = Exception

        class FakeProcess:
            returncode = None

            def poll(self):
                return None

            def terminate(self):
                self.returncode = -15

            def wait(self, timeout=None):
                return self.returncode

        with tempfile.TemporaryDirectory() as temporary_directory:
            config_path = Path(temporary_directory) / "config.toml"
            config_path.write_text('api_key = "test-key"\n', encoding="utf-8")
            session = interactive.InteractiveSession(
                interactive.SearchParams("Example"),
                lambda _params: [],
                config_path,
            )
            session.screen = FakeScreen()
            session.curses = FakeCurses()
            with mock.patch.object(interactive.subprocess, "Popen", return_value=FakeProcess()):
                with self.assertRaises(interactive.CancelledError):
                    session._run_folder_command(["putio"], "Loading folders")

            self.assertEqual(-1, session.screen.timeouts[-1])

    def test_ctrl_c_cancels_folder_discovery_and_reaps_the_child(self):
        class FakeScreen:
            def __init__(self):
                self.timeouts = []

            def getmaxyx(self):
                return 24, 120

            def erase(self):
                pass

            def addnstr(self, *_args):
                pass

            def refresh(self):
                pass

            def timeout(self, value):
                self.timeouts.append(value)

            def getch(self):
                raise KeyboardInterrupt

        class FakeCurses:
            A_BOLD = 0
            A_DIM = 0
            error = Exception

        class FakeProcess:
            returncode = None

            def poll(self):
                return None

            def terminate(self):
                self.returncode = -15

            def wait(self, timeout=None):
                return self.returncode

        with tempfile.TemporaryDirectory() as temporary_directory:
            config_path = Path(temporary_directory) / "config.toml"
            config_path.write_text('api_key = "test-key"\n', encoding="utf-8")
            session = interactive.InteractiveSession(
                interactive.SearchParams("Example"),
                lambda _params: [],
                config_path,
            )
            session.screen = FakeScreen()
            session.curses = FakeCurses()
            process = FakeProcess()
            with mock.patch.object(interactive.subprocess, "Popen", return_value=process):
                with self.assertRaises(KeyboardInterrupt):
                    session._run_folder_command(["putio"], "Loading folders")

            self.assertEqual(-15, process.returncode)
            self.assertEqual(-1, session.screen.timeouts[-1])

    def test_successful_default_action_survives_preference_save_failure(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_path = Path(temporary_directory) / "config.toml"
            config_path.write_text('api_key = "test-key"\n', encoding="utf-8")
            session = interactive.InteractiveSession(
                interactive.SearchParams("Example"),
                lambda _params: [],
                config_path,
            )
            session._confirm = mock.Mock(return_value=True)
            session._show_message = mock.Mock()
            completed = SimpleNamespace(returncode=0, stderr="")
            with mock.patch.object(
                interactive.subprocess, "run", return_value=completed
            ), mock.patch.object(
                interactive, "update_toml_sections", side_effect=OSError("read-only config")
            ):
                session._activate_default("magnet:?xt=urn:btih:example")

            self.assertIn("Opened with the system default application.", session.status)
            self.assertIn("Preference was not saved", session.status)

    def test_successful_putio_transfer_survives_preference_save_failure(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_path = Path(temporary_directory) / "config.toml"
            config_path.write_text('api_key = "test-key"\n', encoding="utf-8")
            session = interactive.InteractiveSession(
                interactive.SearchParams("Example"),
                lambda _params: [],
                config_path,
            )
            session._discover_putio_folders = mock.Mock(
                return_value=[interactive.PutioFolder(0, "Root")]
            )
            session._choose_folder = mock.Mock(return_value=interactive.PutioFolder(0, "Root"))
            session._confirm = mock.Mock(return_value=True)
            session._draw_loading = mock.Mock()
            session._show_message = mock.Mock()
            completed = SimpleNamespace(returncode=0, stderr="", stdout="{}")
            with mock.patch.object(
                interactive.subprocess, "run", return_value=completed
            ), mock.patch.object(
                interactive, "update_toml_sections", side_effect=OSError("read-only config")
            ):
                session._activate_putio("magnet:?xt=urn:btih:example")

            self.assertIn("Transfer created in Root.", session.status)
            self.assertIn("Preference was not saved", session.status)


@unittest.skipIf(
    sys.platform == "win32", "curses alternate-screen tests require a Unix pseudo-terminal"
)
class InteractivePtyTests(unittest.TestCase):
    """Exercise the real alternate-screen renderer without external dependencies."""

    def test_form_renders_in_a_pty_and_accepts_ctrl_x(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            home = Path(temporary_directory)
            config_path = home / ".config" / "jackett-search" / "config.toml"
            config_path.parent.mkdir(parents=True)
            config_path.write_text('api_key = "test-key"\n', encoding="utf-8")
            child_pid, master = pty.fork()
            if child_pid == 0:
                environment = os.environ | {"HOME": str(home), "TERM": "xterm-256color"}
                os.chdir(ROOT)
                os.execve(
                    sys.executable,
                    [sys.executable, str(SCRIPT), "--interactive"],
                    environment,
                )

            try:
                fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 120, 0, 0))

                rendered = bytearray()
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline and b"New Jackett search" not in rendered:
                    ready, _, _ = select.select([master], [], [], 0.1)
                    if not ready:
                        continue
                    try:
                        rendered.extend(os.read(master, 65536))
                    except OSError as error:
                        if error.errno == errno.EIO:
                            break
                        raise

                self.assertIn(b"New Jackett search", rendered)
                os.write(master, bytes((interactive.CTRL_X,)))
                deadline = time.monotonic() + 2
                while time.monotonic() < deadline and b"Exit interactive mode?" not in rendered:
                    ready, _, _ = select.select([master], [], [], 0.1)
                    if not ready:
                        continue
                    try:
                        rendered.extend(os.read(master, 65536))
                    except OSError as error:
                        if error.errno == errno.EIO:
                            break
                        raise

                self.assertIn(b"Exit interactive mode?", rendered)
            finally:
                if child_pid:
                    try:
                        os.kill(child_pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    try:
                        os.waitpid(child_pid, 0)
                    except ChildProcessError:
                        pass
                os.close(master)


class CliGuardrailTests(unittest.TestCase):
    """Exercise parser-only failures without reading local configuration."""

    def run_cli(self, *arguments):
        with tempfile.TemporaryDirectory() as temporary_directory:
            environment = os.environ.copy()
            environment["HOME"] = temporary_directory
            return subprocess.run(
                [sys.executable, str(SCRIPT), *arguments],
                capture_output=True,
                text=True,
                check=False,
                env=environment,
            )

    def test_interactive_rejects_json_output_mode(self):
        completed = self.run_cli("--interactive", "--json", "Example")
        self.assertEqual(2, completed.returncode)
        self.assertIn("--json and --magnet cannot be used with --interactive", completed.stderr)

    def test_normal_mode_requires_a_query(self):
        completed = self.run_cli()
        self.assertEqual(2, completed.returncode)
        self.assertIn("the following arguments are required: query", completed.stderr)

    def test_clear_history_rejects_search_arguments(self):
        completed = self.run_cli("--clear-history", "--limit", "5")
        self.assertEqual(2, completed.returncode)
        self.assertIn("cannot be combined with search or output arguments", completed.stderr)

    def test_interactive_forwards_cli_search_options_to_the_session(self):
        config_path = Path("config.toml")
        with mock.patch.object(
            cli,
            "load_config",
            return_value=("http://jackett.example.test:9117", "test-key", config_path),
        ), mock.patch.object(cli, "InteractiveSession") as session_class, mock.patch.object(
            sys,
            "argv",
            [
                "jackett-search",
                "--interactive",
                "--torrent-only",
                "--sort",
                "dlf,seeders",
                "--limit",
                "30",
                "--timeout",
                "20",
                "Example",
            ],
        ):
            cli.main()

        initial_params = session_class.call_args.args[0]
        self.assertEqual("Example", initial_params.query)
        self.assertEqual("dlf,seeders", initial_params.sort)
        self.assertEqual(30, initial_params.limit)
        self.assertEqual(20, initial_params.timeout)
        self.assertEqual("torrents", initial_params.result_filter)
        session_class.return_value.run.assert_called_once_with()


class ExistingCliTests(unittest.TestCase):
    """Keep existing non-interactive sorting, formatting, and config behaviour covered."""

    def test_search_progress_reports_completed_indexers(self):
        progress = []
        with mock.patch.object(
            cli, "get_indexer_ids", return_value=["first", "second"]
        ), mock.patch.object(
            cli,
            "query_indexer",
            side_effect=lambda _url, _api_key, indexer_id, _query, _timeout: [
                {"Title": indexer_id, "Seeders": 1}
            ],
        ):
            results = cli.search(
                "Example",
                "http://jackett.example.test:9117",
                "test-key",
                quiet=True,
                progress_callback=lambda completed, total: progress.append((completed, total)),
            )

        self.assertEqual([(0, 2), (1, 2), (2, 2)], progress)
        self.assertEqual({"first", "second"}, {result["Title"] for result in results})

    def test_sorting_and_formatting_behaviour_remain_compatible(self):
        self.assertEqual(
            [("DownloadVolumeFactor", "asc"), ("Seeders", "desc")],
            cli.parse_sort_spec("dlf,seeders"),
        )
        results = [
            {"Title": "low", "Seeders": 1},
            {"Title": "high", "Seeders": 100},
        ]
        self.assertEqual("high", cli.sort_results(results, "seeders")[0]["Title"])
        self.assertEqual("1.0 KB", cli.format_size(1024))

    def test_config_loader_returns_active_path_with_credentials(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            home = Path(temporary_directory)
            config_path = home / ".config" / "jackett-search" / "config.toml"
            config_path.parent.mkdir(parents=True)
            config_path.write_text(
                'url = "http://jackett.example.test:9117"\napi_key = "test-key"\n',
                encoding="utf-8",
            )
            with mock.patch.object(cli.Path, "home", return_value=home):
                url, api_key, active_path = cli.load_config()

            self.assertEqual("http://jackett.example.test:9117", url)
            self.assertEqual("test-key", api_key)
            self.assertEqual(config_path, active_path)


if __name__ == "__main__":
    unittest.main()
