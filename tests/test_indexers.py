"""Network-free coverage for configured indexer selection in CLI and TUI searches."""

import argparse
import io
import json
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "jackett-search"
CLI_LOADER = SourceFileLoader("jackett_search_indexer_tests", str(SCRIPT))
CLI_SPEC = spec_from_loader(CLI_LOADER.name, CLI_LOADER)
assert CLI_SPEC is not None
cli = module_from_spec(CLI_SPEC)
CLI_LOADER.exec_module(cli)

URL = "http://jackett.example.test:9117"
CONFIGURED_IDS = ["1337x", "yts", "other"]


class IndexerSelectionTests(unittest.TestCase):
    def setUp(self):
        patches = {
            "discovery": mock.patch.object(cli, "get_indexer_ids", return_value=CONFIGURED_IDS),
            "query": mock.patch.object(
                cli,
                "query_indexer",
                side_effect=lambda _url, _key, indexer, _query, _timeout: [
                    {"Title": indexer, "Seeders": 1}
                ],
            ),
            "config": mock.patch.object(
                cli, "load_config", return_value=(URL, "test-key", Path("config.toml"))
            ),
            "preferences": mock.patch.object(
                cli,
                "load_interactive_preferences",
                return_value=SimpleNamespace(default_filter="both"),
            ),
            "network": mock.patch.object(
                cli.urllib.request,
                "urlopen",
                side_effect=AssertionError("Unexpected network request"),
            ),
            "config_path": mock.patch.object(
                cli, "find_config_path", side_effect=AssertionError("Unexpected configuration read")
            ),
        }
        for name, patcher in patches.items():
            setattr(self, name, patcher.start())
            self.addCleanup(patcher.stop)

    def run_cli(self, *arguments):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with mock.patch.object(sys, "argv", [str(SCRIPT), *arguments]), redirect_stdout(
            stdout
        ), redirect_stderr(stderr):
            try:
                cli.main()
            except SystemExit as error:
                returncode = error.code
            else:
                returncode = 0
        return SimpleNamespace(
            returncode=returncode, stdout=stdout.getvalue(), stderr=stderr.getvalue()
        )

    def test_parser_trims_and_deduplicates_in_selection_order(self):
        self.assertEqual(["yts", "1337x"], cli.parse_indexers(" yts ,1337x, yts,1337x "))

    def test_parser_rejects_empty_values_and_components(self):
        for value in ("", " ", ",", ",yts", "yts,", "yts,,1337x", "yts, ,1337x"):
            with self.subTest(value=value), self.assertRaisesRegex(
                argparse.ArgumentTypeError, "non-empty configured indexer IDs"
            ):
                cli.parse_indexers(value)

    def test_search_queries_only_selected_indexers_and_counts_their_progress(self):
        for selection, expected in (
            (None, CONFIGURED_IDS),
            (["yts"], ["yts"]),
            (cli.parse_indexers(" yts,1337x,yts "), ["yts", "1337x"]),
        ):
            with self.subTest(selection=selection):
                self.query.reset_mock()
                progress = mock.Mock()
                results = cli.search(
                    "Example", URL, "test-key", indexers=selection, progress_callback=progress
                )
                self.assertCountEqual(expected, [result["Title"] for result in results])
                self.assertCountEqual(
                    [mock.call(URL, "test-key", indexer, "Example", 10) for indexer in expected],
                    self.query.call_args_list,
                )
                self.assertEqual(
                    [mock.call(completed, len(expected)) for completed in range(len(expected) + 1)],
                    progress.call_args_list,
                )

    def test_unknown_selection_fails_before_any_search_or_progress(self):
        for selection in (["missing"], ["yts", "missing"], ["YTS"], ["all"]):
            with self.subTest(selection=selection):
                progress = mock.Mock()
                with self.assertRaisesRegex(ValueError, "Unknown configured indexer ID"):
                    cli.search(
                        "Example", URL, "test-key", indexers=selection, progress_callback=progress
                    )
                self.query.assert_not_called()
                progress.assert_not_called()

    def test_explicit_selection_requires_available_discovery(self):
        self.discovery.return_value = []
        for quiet in (False, True):
            with self.subTest(quiet=quiet), self.assertRaisesRegex(
                ValueError, "Cannot validate --indexer"
            ):
                cli.search("Example", URL, "test-key", indexers=["yts"], quiet=quiet)
        self.query.assert_not_called()

    def test_omitted_selection_preserves_all_fallback_and_quiet_behavior(self):
        self.discovery.return_value = []
        for quiet in (False, True):
            with self.subTest(quiet=quiet):
                self.query.reset_mock()
                stderr = io.StringIO()
                progress = mock.Mock()
                with redirect_stderr(stderr):
                    results = cli.search(
                        "Example", URL, "test-key", quiet=quiet, progress_callback=progress
                    )
                self.query.assert_called_once_with(URL, "test-key", "all", "Example", 10)
                self.assertEqual([{"Title": "all", "Seeders": 1}], results)
                self.assertEqual([mock.call(0, 1), mock.call(1, 1)], progress.call_args_list)
                if quiet:
                    self.assertEqual("", stderr.getvalue())
                else:
                    self.assertIn("falling back to /all", stderr.getvalue())

    def test_selected_search_preserves_filters_sort_limit_and_timeout(self):
        self.query.side_effect = None
        self.query.return_value = [
            {"Title": "large", "Size": 30, "MagnetUri": "magnet:large", "Link": "large"},
            {"Title": "magnet", "Size": 10, "MagnetUri": "magnet:small"},
            {"Title": "torrent", "Size": 20, "Link": "small"},
        ]
        for options, title, timeout in (
            ({"magnets_only": True}, "magnet", 0),
            ({"torrent_only": True}, "torrent", 7),
        ):
            with self.subTest(options=options):
                self.query.reset_mock()
                results = cli.search(
                    "Example",
                    URL,
                    "test-key",
                    indexers=["yts"],
                    timeout=timeout,
                    sort="size:asc",
                    limit=1,
                    quiet=True,
                    **options,
                )
                self.assertEqual([title], [result["Title"] for result in results])
                self.query.assert_called_once_with(URL, "test-key", "yts", "Example", timeout)

    def test_cli_selection_limits_json_results(self):
        completed = self.run_cli("--indexer", " yts,1337x,yts ", "--json", "Example")
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertCountEqual(
            ["yts", "1337x"], [row["title"] for row in json.loads(completed.stdout)]
        )
        self.assertEqual(2, self.query.call_count)
        self.assertIn("Searching 2 indexers", completed.stderr)

    def test_cli_selection_errors_do_not_search(self):
        for configured in (CONFIGURED_IDS, []):
            with self.subTest(configured=configured):
                self.discovery.return_value = configured
                completed = self.run_cli("--indexer", "yts,missing", "--json", "Example")
                self.assertEqual(2, completed.returncode)
                self.assertIn("no torrent search was issued", completed.stderr)
                self.assertNotIn("falling back", completed.stderr)
                self.assertNotIn("Traceback", completed.stderr)
                self.assertEqual("", completed.stdout)
                self.query.assert_not_called()

    def test_help_and_invalid_arguments_do_not_load_credentials(self):
        for arguments, expected_code, expected_text in (
            (("--help",), 0, "--indexer IDS"),
            (("--indexer",), 2, "expected one argument"),
            *(
                (("--indexer", value, "Example"), 2, "non-empty configured indexer IDs")
                for value in ("", " ", ",yts", "yts,", "yts,,1337x", "yts, ,1337x")
            ),
            (("--clear-history", "--indexer", "yts"), 2, "cannot be combined"),
            (("--bitport-auth", "--indexer", "yts"), 2, "cannot be combined"),
        ):
            with self.subTest(arguments=arguments):
                completed = self.run_cli(*arguments)
                self.assertEqual(expected_code, completed.returncode)
                self.assertIn(expected_text, completed.stdout + completed.stderr)
                self.config.assert_not_called()
                self.config_path.assert_not_called()
                self.discovery.assert_not_called()
                self.query.assert_not_called()
                self.network.assert_not_called()

    def test_every_interactive_search_retains_cli_selection(self):
        with mock.patch.object(cli, "InteractiveSession") as session_class:
            completed = self.run_cli("--interactive", "--indexer", " yts,1337x,yts ", "Example")
        self.assertEqual(0, completed.returncode, completed.stderr)
        initial_params, callback, _config_path = session_class.call_args.args
        self.assertIs(callback, session_class.call_args.kwargs["progress_search_callback"])
        session_class.return_value.run.assert_called_once_with()

        with mock.patch.object(cli, "search", wraps=cli.search) as shared_search:
            for params in (initial_params, cli.SearchParams("New query"), initial_params):
                progress = mock.Mock()
                callback(params, progress)
                self.assertEqual(
                    [mock.call(0, 2), mock.call(1, 2), mock.call(2, 2)], progress.call_args_list
                )
            callback(cli.SearchParams("History query"))
        self.assertEqual(4, shared_search.call_count)
        for call in shared_search.call_args_list:
            self.assertEqual(["yts", "1337x"], call.kwargs["indexers"])
            self.assertTrue(call.kwargs["quiet"])
        self.assertEqual(8, self.query.call_count)
        self.assertEqual({"yts", "1337x"}, {call.args[2] for call in self.query.call_args_list})


if __name__ == "__main__":
    unittest.main()
