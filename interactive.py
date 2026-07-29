"""Dependency-free curses interface and state helpers for ``jackett-search``."""

import json
import multiprocessing
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

HISTORY_FILENAME = "history.json"
DEFAULT_HISTORY_LIMIT = 50
MIN_WIDTH = 80
MIN_HEIGHT = 20
FILTER_OPTIONS = ("both", "magnets", "torrents")
# The CLI supports compound sort specifications. The TUI offers every valid
# single-field ordering as a selector, keeping the form discoverable.
SORT_OPTIONS = (
    "seeders",
    "seeders:asc",
    "leechers",
    "leechers:asc",
    "grabs",
    "grabs:asc",
    "size",
    "size:asc",
    "published",
    "published:asc",
    "files",
    "files:asc",
    "dlf",
    "dlf:desc",
    "ulf",
    "ulf:asc",
    "tracker",
    "tracker:desc",
    "title",
    "title:desc",
)
SELECTOR_FIELDS = frozenset({"Sort", "Filter"})
NUMERIC_FIELDS = frozenset({"Limit", "Timeout"})
FORM_FIELD_LABELS = {
    "Query": "Query",
    "Sort": "Sort",
    "Limit": "Limit (results)",
    "Timeout": "Timeout (seconds)",
    "Filter": "Filter",
}
FORM_LABEL_WIDTH = max(len(label) for label in FORM_FIELD_LABELS.values())
CTRL_X = 24
RESULT_TITLE_WIDTH = 52
RESULT_SIZE_WIDTH = 10
RESULT_SEEDS_WIDTH = 6
RESULT_LEECHERS_WIDTH = 5
RESULT_GRABS_WIDTH = 6
RESULT_DLF_WIDTH = 5
RESULT_TRACKER_WIDTH = 20
RESULT_MAGNET_ACTION_WIDTH = 11
RESULT_TORRENT_ACTION_WIDTH = 12
COMPACT_RESULT_TITLE_MIN_WIDTH = 14
COMPACT_RESULT_SIZE_WIDTH = 8
COMPACT_RESULT_NUMERIC_WIDTH = 4
COMPACT_RESULT_DLF_WIDTH = 5
COMPACT_RESULT_TRACKER_WIDTH = 8


@dataclass(frozen=True)
class ResultTableLayout:
    """Column widths for either the full or compact results table."""

    number_width: int
    title_width: int
    size_width: int
    seeds_width: int
    leechers_width: int
    grabs_width: int
    dlf_width: int
    tracker_width: int
    magnet_action_width: int
    torrent_action_width: int
    compact_actions: bool


class InteractiveUnavailableError(RuntimeError):
    """Raised when the terminal cannot host the interactive interface."""


class CancelledError(RuntimeError):
    """Raised when a cancellable put.io folder lookup is cancelled."""


class ExitInteractiveMode(RuntimeError):
    """Raised after the user confirms a Ctrl-X request to leave the TUI."""


def cycle_option(options: Sequence[str], value: str, step: int) -> str:
    """Return the adjacent selector option, defaulting unknown values safely."""
    try:
        index = options.index(value)
    except ValueError:
        return options[0] if step > 0 else options[-1]
    return options[(index + step) % len(options)]


def accepts_field_character(field: str, character: str) -> bool:
    """Return whether a form field accepts a printable character."""
    return field not in NUMERIC_FIELDS or character.isdigit()


def adjust_numeric_value(value: str, delta: int) -> str:
    """Return a non-negative spinner value, retaining an empty Limit as no cap."""
    if delta not in {-1, 1}:
        raise ValueError("Numeric field adjustments must increment or decrement by one.")
    if not value:
        return "1" if delta > 0 else ""
    return str(max(0, int(value) + delta))


@dataclass
class SearchParams:
    """Search settings that can be edited and persisted by the interactive form."""

    query: str = ""
    sort: str = "seeders"
    limit: Optional[int] = None
    timeout: int = 10
    result_filter: str = "both"

    def to_history(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "sort": self.sort,
            "limit": self.limit,
            "timeout": self.timeout,
            "result_filter": self.result_filter,
        }

    @classmethod
    def from_history(cls, value: Dict[str, Any]) -> Optional["SearchParams"]:
        try:
            query = value["query"]
            sort = value.get("sort", "seeders")
            limit = value.get("limit")
            timeout = value.get("timeout", 10)
            result_filter = value.get("result_filter", "both")
        except (AttributeError, KeyError, TypeError):
            return None
        if not isinstance(query, str) or not isinstance(sort, str):
            return None
        if limit is not None and (not isinstance(limit, int) or limit < 0):
            return None
        if not isinstance(timeout, int) or timeout < 0:
            return None
        if result_filter not in {"both", "magnets", "torrents"}:
            return None
        return cls(query, sort, limit, timeout, result_filter)


def _run_search_worker(
    search_callback: Callable[[SearchParams], List[Dict[str, Any]]],
    progress_search_callback: Optional[
        Callable[[SearchParams, Callable[[int, int], None]], List[Dict[str, Any]]]
    ],
    params: SearchParams,
    sender: Any,
) -> None:
    """Run a search outside curses so the parent can terminate it on Esc."""

    def report_progress(completed: int, total: int) -> None:
        sender.send(("progress", (completed, total)))

    try:
        if progress_search_callback is None:
            results = search_callback(params)
        else:
            results = progress_search_callback(params, report_progress)
        sender.send(("results", results))
    except Exception as error:
        sender.send(("error", str(error)))
    finally:
        sender.close()


@dataclass
class InteractivePreferences:
    """Interactive-only preferences, kept separate from Jackett credentials."""

    persist_query_history: bool = True
    history_limit: int = DEFAULT_HISTORY_LIMIT
    last_client: Optional[str] = None
    putio_last_folder_id: Optional[int] = None


@dataclass
class PutioFolder:
    """A visible put.io destination folder with a stable API ID and full path."""

    id: int
    path: str


def history_path_for(config_path: Optional[Path]) -> Path:
    """Return the history file beside the active config, defaulting to XDG."""
    if config_path is not None:
        return config_path.parent / HISTORY_FILENAME
    return Path.home() / ".config" / "jackett-search" / HISTORY_FILENAME


def _toml_scalar(raw: str) -> Any:
    value = raw.strip().split("#", 1)[0].strip()
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value[1:-1]
    return value


def read_toml_sections(config_path: Optional[Path]) -> Dict[str, Dict[str, Any]]:
    """Read the small TOML subset used by this dependency-free project."""
    sections: Dict[str, Dict[str, Any]] = {"": {}}
    if config_path is None or not config_path.exists():
        return sections

    current = ""
    section_re = re.compile(r"^\s*\[([^]]+)]\s*(?:#.*)?$")
    key_re = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")
    for raw_line in config_path.read_text(encoding="utf-8").splitlines():
        section_match = section_re.match(raw_line)
        if section_match:
            current = section_match.group(1).strip()
            sections.setdefault(current, {})
            continue
        key_match = key_re.match(raw_line)
        if key_match:
            sections.setdefault(current, {})[key_match.group(1)] = _toml_scalar(key_match.group(2))
    return sections


def load_interactive_preferences(config_path: Optional[Path]) -> InteractivePreferences:
    """Load interactive preferences without reading or exposing credentials."""
    sections = read_toml_sections(config_path)
    interactive = sections.get("interactive", {})
    putio = sections.get("interactive.clients.putio", {})
    preference = InteractivePreferences()
    if isinstance(interactive.get("persist_query_history"), bool):
        preference.persist_query_history = interactive["persist_query_history"]
    if isinstance(interactive.get("history_limit"), int) and interactive["history_limit"] > 0:
        preference.history_limit = interactive["history_limit"]
    if isinstance(interactive.get("last_client"), str):
        preference.last_client = interactive["last_client"]
    if isinstance(putio.get("last_folder_id"), int) and putio["last_folder_id"] >= 0:
        preference.putio_last_folder_id = putio["last_folder_id"]
    return preference


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    return json.dumps(str(value))


def update_toml_sections(config_path: Path, updates: Dict[str, Dict[str, Any]]) -> None:
    """Update selected simple TOML values while leaving unrelated config intact."""
    if not config_path.exists():
        return
    lines = config_path.read_text(encoding="utf-8").splitlines()
    section_re = re.compile(r"^\s*\[([^]]+)]\s*(?:#.*)?$")
    key_re = re.compile(r"^(\s*)([A-Za-z_][A-Za-z0-9_]*)(\s*=\s*).*?$")
    current = ""
    seen: Dict[str, set] = {section: set() for section in updates}

    for index, line in enumerate(lines):
        section_match = section_re.match(line)
        if section_match:
            current = section_match.group(1).strip()
            continue
        if current not in updates:
            continue
        key_match = key_re.match(line)
        if key_match and key_match.group(2) in updates[current]:
            key = key_match.group(2)
            lines[index] = (
                f"{key_match.group(1)}{key}{key_match.group(3)}{_toml_value(updates[current][key])}"
            )
            seen[current].add(key)

    for section, values in updates.items():
        missing = [key for key in values if key not in seen[section]]
        if not missing:
            continue
        section_found = False
        current = ""
        insert_at = len(lines)
        for index, line in enumerate(lines):
            section_match = section_re.match(line)
            if section_match:
                if current == section:
                    insert_at = index
                    section_found = True
                    break
                current = section_match.group(1).strip()
                if current == section:
                    section_found = True
                    insert_at = index + 1
        if not section_found:
            if lines and lines[-1] != "":
                lines.append("")
            lines.append(f"[{section}]")
            insert_at = len(lines)
        for key in missing:
            lines.insert(insert_at, f"{key} = {_toml_value(values[key])}")
            insert_at += 1

    mode = config_path.stat().st_mode & 0o777
    descriptor, temporary_name = tempfile.mkstemp(prefix=".config-", dir=str(config_path.parent))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as temporary:
            temporary.write("\n".join(lines) + "\n")
        os.chmod(temporary_name, mode)
        os.replace(temporary_name, config_path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def load_history(history_path: Path) -> List[SearchParams]:
    """Load valid saved queries, ignoring corrupt or old history safely."""
    if not history_path.exists():
        return []
    try:
        loaded = json.loads(history_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    if not isinstance(loaded, list):
        return []
    history = []
    for entry in loaded:
        parsed = SearchParams.from_history(entry)
        if parsed is not None:
            history.append(parsed)
    return history


def save_history(history_path: Path, entries: Iterable[SearchParams], limit: int) -> None:
    """Atomically save a bounded history file with restrictive permissions."""
    history_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    unique: List[SearchParams] = []
    seen = set()
    for entry in entries:
        key = tuple(sorted(entry.to_history().items()))
        if key not in seen:
            unique.append(entry)
            seen.add(key)
        if len(unique) >= limit:
            break

    descriptor, temporary_name = tempfile.mkstemp(prefix=".history-", dir=str(history_path.parent))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as temporary:
            json.dump([entry.to_history() for entry in unique], temporary, indent=2)
            temporary.write("\n")
        os.chmod(temporary_name, 0o600)
        os.replace(temporary_name, history_path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def record_history(
    history: Sequence[SearchParams], params: SearchParams, limit: int
) -> List[SearchParams]:
    """Return a most-recent-first, deduplicated bounded query history."""
    key = params.to_history()
    return [params] + [entry for entry in history if entry.to_history() != key][: limit - 1]


def clear_history(history_path: Path) -> bool:
    """Delete persisted history if it exists, returning whether anything changed."""
    try:
        history_path.unlink()
    except FileNotFoundError:
        return False
    return True


def available_clients() -> List[Tuple[str, str]]:
    """Return installed, supported client handlers in display order."""
    clients = []
    if shutil.which("putio"):
        clients.append(("putio", "put.io"))
    default_command = "open" if sys.platform == "darwin" else "xdg-open"
    if shutil.which(default_command):
        clients.append(("default", "System default application"))
    return clients


def clipboard_command() -> Optional[List[str]]:
    """Return the first usable clipboard command for the active platform."""
    if sys.platform == "darwin" and shutil.which("pbcopy"):
        return ["pbcopy"]
    if shutil.which("wl-copy"):
        return ["wl-copy"]
    if shutil.which("xclip"):
        return ["xclip", "-selection", "clipboard"]
    if shutil.which("xsel"):
        return ["xsel", "--clipboard", "--input"]
    return None


def copy_to_clipboard(url: str) -> Tuple[bool, str]:
    """Copy a URL without involving a shell or writing it to history."""
    command = clipboard_command()
    if command is None:
        return False, "No supported clipboard command is available."
    completed = subprocess.run(command, input=url, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        return False, (completed.stderr.strip() or "Clipboard command failed.")
    return True, "URL copied to clipboard."


def parse_putio_folders(payload: Dict[str, Any], parent_path: str) -> List[PutioFolder]:
    """Translate one put.io folder-list payload into direct child folder paths."""
    folders = []
    for item in payload.get("files", []):
        if item.get("file_type") != "FOLDER" or item.get("is_hidden"):
            continue
        try:
            folder_id = int(item["id"])
        except (KeyError, TypeError, ValueError):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        path = f"{parent_path}/{name}" if parent_path else name
        folders.append(PutioFolder(folder_id, path))
    return folders


def putio_add_command(url: str, folder_id: int) -> List[str]:
    """Build the argv for an intentional put.io transfer submission."""
    return [
        "putio",
        "transfers",
        "add",
        "--url",
        url,
        "--save-parent-id",
        str(folder_id),
        "--output",
        "json",
    ]


def putio_cancel_command(transfer_id: int) -> List[str]:
    """Build the argv for a reversible post-submit put.io cancellation."""
    return ["putio", "transfers", "cancel", "--id", str(transfer_id), "--output", "json"]


def _transfer_id(payload: Dict[str, Any]) -> Optional[int]:
    """Extract a transfer ID from current and likely future put.io CLI JSON shapes."""
    candidates = [payload, payload.get("transfer"), payload.get("data")]
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        try:
            return int(candidate["id"])
        except (KeyError, TypeError, ValueError):
            continue
    return None


def _truncate(value: str, width: int) -> str:
    """Truncate visible text without creating invalid negative-width slices."""
    if width <= 0:
        return ""
    if len(value) <= width:
        return value
    if width <= 3:
        return value[:width]
    return value[: width - 3] + "..."


def _middle_truncate(value: str, width: int) -> str:
    """Keep both ends of long folder paths visible in constrained terminals."""
    if width <= 0:
        return ""
    if len(value) <= width:
        return value
    if width <= 3:
        return value[:width]
    left = (width - 3) // 2
    return value[:left] + "..." + value[-(width - 3 - left) :]


class InteractiveSession:
    """A single curses session; actions operate on one result at a time."""

    def __init__(
        self,
        initial_params: SearchParams,
        search_callback: Callable[[SearchParams], List[Dict[str, Any]]],
        config_path: Path,
        progress_search_callback: Optional[
            Callable[[SearchParams, Callable[[int, int], None]], List[Dict[str, Any]]]
        ] = None,
    ) -> None:
        self.params = initial_params
        self.search_callback = search_callback
        self.progress_search_callback = progress_search_callback
        self.config_path = config_path
        self.preferences = load_interactive_preferences(config_path)
        self.history_path = history_path_for(config_path)
        self.history = load_history(self.history_path)
        self.results: List[Dict[str, Any]] = []
        self.cursor_index = 0
        self.marked_indices: set = set()  # Reserved for a future batch-selection mode.
        self.focused_action = "magnet"
        self.status = ""
        self.screen: Any = None
        self.curses: Any = None
        self.colour_attributes: Dict[str, int] = {}

    def run(self) -> None:
        """Start a guarded full-screen curses lifecycle."""
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            raise InteractiveUnavailableError("--interactive requires an interactive terminal.")
        try:
            import curses
        except ImportError as error:
            raise InteractiveUnavailableError(
                "Interactive mode requires a working curses-capable terminal."
            ) from error
        self.curses = curses
        try:
            curses.wrapper(self._run)
        except KeyboardInterrupt:
            # ``wrapper`` restores the terminal before propagating Ctrl-C.
            return
        except ExitInteractiveMode:
            return
        except curses.error as error:
            raise InteractiveUnavailableError(
                "Interactive mode requires a working curses-capable terminal."
            ) from error

    def _run(self, screen: Any) -> None:
        self.screen = screen
        screen.keypad(True)
        screen.timeout(-1)
        self._configure_colours()
        try:
            self.curses.curs_set(0)
        except self.curses.error:
            pass
        if self.params.query:
            self._perform_search(record=True)
        else:
            if not self._search_form(allow_cancel=False):
                return

        while True:
            self._draw_results()
            key = screen.getch()
            if key == CTRL_X:
                self._request_exit()
            if key == ord("q"):
                return
            if key == 27:
                if self._confirm_search_transition(
                    "Leave current search?",
                    "Return to the search form and keep this interactive session open.",
                ):
                    self._search_form(allow_cancel=True)
            elif key == ord("?"):
                self._show_help()
            elif key == ord("n"):
                self._search_form(allow_cancel=True)
            elif key == ord("r"):
                self._perform_search(record=True)
            elif key in (self.curses.KEY_UP, ord("k")):
                self._move_cursor(-1)
            elif key in (self.curses.KEY_DOWN, ord("j")):
                self._move_cursor(1)
            elif key in (self.curses.KEY_PPAGE, 21):
                self._move_cursor(-self._page_size(half=True))
            elif key in (self.curses.KEY_NPAGE, 4):
                self._move_cursor(self._page_size(half=True))
            elif key in (self.curses.KEY_HOME, ord("g")):
                self.cursor_index = 0
            elif key in (self.curses.KEY_END, ord("G")):
                self.cursor_index = max(0, len(self.results) - 1)
            elif key in (self.curses.KEY_LEFT, ord("h")):
                self._move_action(-1)
            elif key in (self.curses.KEY_RIGHT, ord("l")):
                self._move_action(1)
            elif key == ord("c"):
                self._copy_focused_url()
            elif key in (10, 13, self.curses.KEY_ENTER):
                self._activate_focused_action()

    def _terminal_ready(self) -> bool:
        height, width = self.screen.getmaxyx()
        return width >= MIN_WIDTH and height >= MIN_HEIGHT

    def _clear(self) -> None:
        self.screen.erase()

    def _add(self, row: int, column: int, text: str, attributes: int = 0) -> None:
        height, width = self.screen.getmaxyx()
        if row < 0 or row >= height or column >= width:
            return
        try:
            self.screen.addnstr(
                row,
                column,
                _truncate(text, width - column - 1),
                width - column - 1,
                attributes,
            )
        except self.curses.error:
            pass

    def _minimum_size_message(self) -> None:
        self._clear()
        self._add(
            0,
            0,
            f"Terminal too small. Resize to {MIN_WIDTH}x{MIN_HEIGHT}; Ctrl-X/Ctrl-C exit.",
        )
        self.screen.refresh()

    def _page_size(self, half: bool = False) -> int:
        height, _ = self.screen.getmaxyx()
        rows = max(1, height - 7)
        return max(1, rows // 2) if half else rows

    def _move_cursor(self, delta: int) -> None:
        if not self.results:
            return
        self.cursor_index = max(0, min(len(self.results) - 1, self.cursor_index + delta))
        self._ensure_action_available()

    def _available_actions(self) -> List[str]:
        if not self.results:
            return []
        row = self.results[self.cursor_index]
        return [
            action for action, key in (("magnet", "MagnetUri"), ("torrent", "Link")) if row.get(key)
        ]

    def _ensure_action_available(self) -> None:
        available = self._available_actions()
        if available and self.focused_action not in available:
            self.focused_action = available[0]

    def _move_action(self, direction: int) -> None:
        actions = self._available_actions()
        if not actions:
            return
        self.focused_action = actions[
            (actions.index(self.focused_action) + direction) % len(actions)
        ]

    def _configure_colours(self) -> None:
        """Configure the same semantic colours as the non-interactive table."""
        self.colour_attributes = {}
        has_colours = getattr(self.curses, "has_colors", None)
        if not callable(has_colours) or not has_colours():
            return
        try:
            self.curses.start_color()
            use_default_colours = getattr(self.curses, "use_default_colors", None)
            if callable(use_default_colours):
                use_default_colours()
            self.curses.init_pair(1, self.curses.COLOR_GREEN, -1)
            self.curses.init_pair(2, self.curses.COLOR_YELLOW, -1)
            self.curses.init_pair(3, self.curses.COLOR_RED, -1)
            self.curses.init_pair(4, self.curses.COLOR_CYAN, -1)
            self.colour_attributes = {
                "green": self.curses.color_pair(1),
                "yellow": self.curses.color_pair(2),
                "red": self.curses.color_pair(3),
                "cyan": self.curses.color_pair(4),
            }
        except self.curses.error:
            self.colour_attributes = {}

    def _colour_attribute(self, name: str) -> int:
        return self.colour_attributes.get(name, 0)

    @staticmethod
    def _result_table_content_width(layout: ResultTableLayout) -> int:
        """Return the exact number of columns occupied by a result row."""
        if layout.compact_actions:
            return (
                layout.number_width
                + 1
                + layout.title_width
                + 1
                + layout.size_width
                + 1
                + layout.seeds_width
                + 1
                + layout.leechers_width
                + 1
                + layout.grabs_width
                + 1
                + layout.dlf_width
                + 1
                + layout.tracker_width
                + 1
                + layout.magnet_action_width
                + 1
                + layout.torrent_action_width
            )
        return (
            layout.number_width
            + 1
            + layout.title_width
            + 1
            + layout.size_width
            + 2
            + layout.seeds_width
            + layout.leechers_width
            + layout.grabs_width
            + 2
            + layout.dlf_width
            + 2
            + layout.tracker_width
            + 2
            + layout.magnet_action_width
            + 1
            + layout.torrent_action_width
        )

    def _result_table_layout(self, width: int) -> ResultTableLayout:
        """Keep URL actions visible in every terminal accepted by the TUI."""
        full = ResultTableLayout(
            number_width=4,
            title_width=RESULT_TITLE_WIDTH,
            size_width=RESULT_SIZE_WIDTH,
            seeds_width=RESULT_SEEDS_WIDTH,
            leechers_width=RESULT_LEECHERS_WIDTH,
            grabs_width=RESULT_GRABS_WIDTH,
            dlf_width=RESULT_DLF_WIDTH,
            tracker_width=RESULT_TRACKER_WIDTH,
            magnet_action_width=RESULT_MAGNET_ACTION_WIDTH,
            torrent_action_width=RESULT_TORRENT_ACTION_WIDTH,
            compact_actions=False,
        )
        # ``_add`` deliberately leaves the rightmost terminal cell unused, so
        # the full layout needs one extra available terminal column.
        if width - 1 >= self._result_table_content_width(full):
            return full

        compact_without_title = ResultTableLayout(
            number_width=3,
            title_width=0,
            size_width=COMPACT_RESULT_SIZE_WIDTH,
            seeds_width=COMPACT_RESULT_NUMERIC_WIDTH,
            leechers_width=COMPACT_RESULT_NUMERIC_WIDTH,
            grabs_width=COMPACT_RESULT_NUMERIC_WIDTH,
            dlf_width=COMPACT_RESULT_DLF_WIDTH,
            tracker_width=COMPACT_RESULT_TRACKER_WIDTH,
            magnet_action_width=3,
            torrent_action_width=3,
            compact_actions=True,
        )
        title_width = max(
            COMPACT_RESULT_TITLE_MIN_WIDTH,
            min(
                RESULT_TITLE_WIDTH,
                width - 1 - self._result_table_content_width(compact_without_title),
            ),
        )
        return ResultTableLayout(
            number_width=compact_without_title.number_width,
            title_width=title_width,
            size_width=compact_without_title.size_width,
            seeds_width=compact_without_title.seeds_width,
            leechers_width=compact_without_title.leechers_width,
            grabs_width=compact_without_title.grabs_width,
            dlf_width=compact_without_title.dlf_width,
            tracker_width=compact_without_title.tracker_width,
            magnet_action_width=compact_without_title.magnet_action_width,
            torrent_action_width=compact_without_title.torrent_action_width,
            compact_actions=True,
        )

    def _action_label(self, action: str, available: bool, selected: bool, compact: bool) -> str:
        """Render a stable-width action label with an unambiguous focus state."""
        if compact:
            label = action[0].upper() if available else "—"
            return f"[{label}]" if selected else f" {label} "
        label = f"{action[0].upper()} {action}" if available else f"{action[0].upper()} —"
        return f"[{label}]" if selected else label

    def _draw_action_cell(
        self,
        row: int,
        column: int,
        result: Dict[str, Any],
        selected: bool,
        layout: ResultTableLayout,
    ) -> None:
        """Draw magnet and torrent availability separately so focus is obvious."""
        row_attribute = self.curses.A_REVERSE if selected else 0
        action_specs = (
            (
                "magnet",
                bool(result.get("MagnetUri")),
                layout.magnet_action_width,
                "cyan",
            ),
            (
                "torrent",
                bool(result.get("Link")),
                layout.torrent_action_width,
                "yellow",
            ),
        )
        for action, available, action_width, colour in action_specs:
            focused = selected and self.focused_action == action and available
            label = self._action_label(action, available, focused, layout.compact_actions)
            style = self._colour_attribute(colour) if available else self.curses.A_DIM
            if focused:
                style |= self.curses.A_BOLD | getattr(self.curses, "A_UNDERLINE", 0)
            self._add(row, column, f"{label:<{action_width}}", row_attribute | style)
            column += action_width + 1

    def _draw_results(self) -> None:
        if not self._terminal_ready():
            self._minimum_size_message()
            return
        try:
            self.curses.curs_set(0)
        except self.curses.error:
            pass
        self._clear()
        height, width = self.screen.getmaxyx()
        layout = self._result_table_layout(width)
        heading = f"jackett-search interactive — {len(self.results)} result(s)"
        self._add(0, 0, heading, self.curses.A_BOLD)
        if layout.compact_actions:
            header = (
                f"{'#':<{layout.number_width}} {'Title':<{layout.title_width}} "
                f"{'Size':>{layout.size_width}} {'S':>{layout.seeds_width}} "
                f"{'L':>{layout.leechers_width}} {'G':>{layout.grabs_width}} "
                f"{'DLF':>{layout.dlf_width}} {'Tracker':<{layout.tracker_width}} M/T"
            )
        else:
            header = (
                f"{'#':<{layout.number_width}} {'Title':<{layout.title_width}} "
                f"{'Size':>{layout.size_width}}  {'S':>{layout.seeds_width}}"
                f"{'L':>{layout.leechers_width}}{'G':>{layout.grabs_width}}  "
                f"{'DLF':>{layout.dlf_width}}  {'Tracker':<{layout.tracker_width}}  DL"
            )
        self._add(1, 0, header, self.curses.A_BOLD)
        self._add(2, 0, "─" * (width - 1), self.curses.A_DIM)
        visible = self._page_size()
        top = max(0, min(self.cursor_index - visible // 2, max(0, len(self.results) - visible)))
        if not self.results:
            self._add(4, 0, "No results found. Press n for a new search or q to quit.")
        for offset, result in enumerate(self.results[top : top + visible]):
            index = top + offset
            row = 3 + offset
            selected = index == self.cursor_index
            row_attribute = self.curses.A_REVERSE if selected else 0
            number = _truncate(str(index + 1), layout.number_width)
            raw_title = _truncate(str(result.get("Title") or "Untitled"), layout.title_width)
            title = f"{raw_title:<{layout.title_width}}"
            size_text = _truncate(self._format_size(result.get("Size")), layout.size_width)
            size = f"{size_text:>{layout.size_width}}"
            seeds = int(result.get("Seeders") or 0)
            leechers = int(result.get("Peers") or 0)
            grabs = int(result.get("Grabs") or 0)
            raw_dlf = result.get("DownloadVolumeFactor")
            if raw_dlf is None:
                dlf = "?"
                dlf_attribute = self.curses.A_DIM
            elif raw_dlf == 0.0:
                dlf = "FREE"
                dlf_attribute = self._colour_attribute("green") | self.curses.A_BOLD
            else:
                dlf = f"{raw_dlf:.1f}"
                dlf_attribute = 0
            seed_attribute = self._colour_attribute("red") | self.curses.A_DIM
            if seeds >= 100:
                seed_attribute = self._colour_attribute("green") | self.curses.A_BOLD
            elif seeds >= 10:
                seed_attribute = self._colour_attribute("yellow")
            tracker = _truncate(str(result.get("Tracker") or ""), layout.tracker_width)
            seeds_text = _truncate(str(seeds), layout.seeds_width)
            leechers_text = _truncate(str(leechers), layout.leechers_width)
            grabs_text = _truncate(str(grabs), layout.grabs_width)
            dlf_text = _truncate(dlf, layout.dlf_width)
            title_attribute = getattr(self.curses, "A_UNDERLINE", 0) if result.get("Details") else 0
            if layout.compact_actions:
                cells = (
                    (f"{number:<{layout.number_width}} ", 0),
                    (f"{title} ", title_attribute),
                    (f"{size} ", 0),
                    (f"{seeds_text:>{layout.seeds_width}} ", seed_attribute),
                    (f"{leechers_text:>{layout.leechers_width}} ", self.curses.A_DIM),
                    (f"{grabs_text:>{layout.grabs_width}} ", self.curses.A_DIM),
                    (f"{dlf_text:>{layout.dlf_width}} ", dlf_attribute),
                    (f"{tracker:<{layout.tracker_width}} ", 0),
                )
            else:
                cells = (
                    (f"{number:<{layout.number_width}} ", 0),
                    (f"{title} ", title_attribute),
                    (f"{size}  ", 0),
                    (f"{seeds_text:>{layout.seeds_width}}", seed_attribute),
                    (f"{leechers_text:>{layout.leechers_width}}", self.curses.A_DIM),
                    (f"{grabs_text:>{layout.grabs_width}}  ", self.curses.A_DIM),
                    (f"{dlf_text:>{layout.dlf_width}}  ", dlf_attribute),
                    (f"{tracker:<{layout.tracker_width}}  ", 0),
                )
            column = 0
            for text, attribute in cells:
                self._add(row, column, text, row_attribute | attribute)
                column += len(text)
            self._draw_action_cell(row, column, result, selected, layout)
        self._add(
            height - 3,
            0,
            "↑↓/jk rows  ←→/hl focus Magnet/Torrent  PgUp/PgDn  Home/End  Enter activate  c copy",
        )
        self._add(
            height - 2,
            0,
            "n new search  Esc return  Ctrl-X exit  r refresh  ? help  q/Ctrl-C quit",
            self.curses.A_DIM,
        )
        status = self.status or self._selected_summary()
        self._add(height - 1, 0, _truncate(status, width - 1), self.curses.A_BOLD)
        self.screen.refresh()

    @staticmethod
    def _format_size(value: Any) -> str:
        if not isinstance(value, (int, float)):
            return "?"
        size = float(value)
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"

    def _selected_summary(self) -> str:
        if not self.results:
            return ""
        title = str(self.results[self.cursor_index].get("Title") or "Untitled")
        return f"Selected: {_truncate(title, 70)} — Focus: {self.focused_action.title()} URL"

    def _draw_loading(
        self,
        message: str,
        progress: Optional[Tuple[int, int]] = None,
        spinner_index: int = 0,
        activity: str = "Working",
    ) -> None:
        self._clear()
        _, width = self.screen.getmaxyx()
        spinner = "|/-\\"[spinner_index % 4]
        self._add(0, 0, "jackett-search interactive", self.curses.A_BOLD)
        self._add(2, 0, f"{message} {spinner}")
        hint_row = 6
        if progress is None:
            self._add(4, 0, f"{spinner} {activity}…")
        else:
            completed, total = progress
            remaining = max(0, total - completed)
            bar_width = max(10, min(40, width - 2))
            filled = 0 if total == 0 else round(bar_width * completed / total)
            bar = "#" * filled + "-" * (bar_width - filled)
            self._add(4, 0, f"Indexers {completed}/{total} ({remaining} remaining)")
            self._add(5, 0, f"[{bar}]")
            hint_row = 7
        self._add(
            hint_row,
            0,
            "Esc confirms cancellation. Ctrl-X confirms exit; Ctrl-C exits.",
            self.curses.A_DIM,
        )
        self.screen.refresh()

    def _perform_search(self, record: bool) -> bool:
        progress: Optional[Tuple[int, int]] = None
        spinner_index = 0
        self._draw_loading(
            f"Searching for: {self.params.query}",
            progress,
            spinner_index,
            "Discovering configured indexers",
        )
        try:
            context = multiprocessing.get_context("fork")
        except ValueError as error:
            raise InteractiveUnavailableError(
                "Interactive search cancellation requires fork-capable multiprocessing."
            ) from error
        receiver, sender = context.Pipe(duplex=False)
        process = context.Process(
            target=_run_search_worker,
            args=(self.search_callback, self.progress_search_callback, self.params, sender),
            daemon=True,
        )
        process.start()
        sender.close()
        result_type = "error"
        result_value: Any = "Search worker ended without a result."
        terminal_message_received = False
        try:
            while True:
                while receiver.poll():
                    try:
                        message_type, message_value = receiver.recv()
                    except EOFError:
                        break
                    if message_type == "progress":
                        progress = message_value
                        spinner_index += 1
                        self._draw_loading(
                            f"Searching for: {self.params.query}",
                            progress,
                            spinner_index,
                            "Discovering configured indexers",
                        )
                        continue
                    result_type, result_value = message_type, message_value
                    terminal_message_received = True
                    break
                if terminal_message_received or not process.is_alive():
                    break
                self.screen.timeout(100)
                key = self.screen.getch()
                if key == CTRL_X:
                    if self._confirm_exit():
                        self._stop_search_worker(process)
                        raise ExitInteractiveMode()
                    self._draw_loading(
                        f"Searching for: {self.params.query}",
                        progress,
                        spinner_index,
                        "Discovering configured indexers",
                    )
                    continue
                if key == 27:
                    if not self._confirm_search_transition(
                        "Cancel active search?",
                        "This stops the current Jackett search and returns to its results.",
                    ):
                        self._draw_loading(
                            f"Searching for: {self.params.query}",
                            progress,
                            spinner_index,
                            "Discovering configured indexers",
                        )
                        continue
                    self._stop_search_worker(process)
                    self.status = "Search cancelled."
                    return False
                spinner_index += 1
                self._draw_loading(
                    f"Searching for: {self.params.query}",
                    progress,
                    spinner_index,
                    "Discovering configured indexers",
                )
        except (ExitInteractiveMode, KeyboardInterrupt):
            if process.is_alive():
                self._stop_search_worker(process)
            raise
        finally:
            process.join()
            receiver.close()
            self.screen.timeout(-1)

        if result_type == "error":
            self.results = []
            self.status = f"Search error: {result_value}"
        else:
            self.results = result_value
            self.status = f"Search complete: {len(self.results)} result(s)."
            if record and self.params.query.strip():
                self.history = record_history(
                    self.history, self.params, self.preferences.history_limit
                )
                if self.preferences.persist_query_history:
                    try:
                        save_history(
                            self.history_path, self.history, self.preferences.history_limit
                        )
                    except OSError as error:
                        self.status = f"Search complete, but history was not saved: {error}"
        self.cursor_index = 0
        self.focused_action = "magnet"
        self._ensure_action_available()
        return True

    @staticmethod
    def _stop_search_worker(process: multiprocessing.Process) -> None:
        """Terminate an active search worker without leaving it to finish in the background."""
        process.terminate()
        process.join(timeout=5)
        if process.is_alive():
            process.kill()
            process.join()

    def _search_form(self, allow_cancel: bool) -> bool:
        values = {
            "Query": self.params.query,
            "Sort": self.params.sort,
            "Limit": "" if self.params.limit is None else str(self.params.limit),
            "Timeout": str(self.params.timeout),
            "Filter": self.params.result_filter,
        }
        fields = list(values)
        positions = {field: len(value) for field, value in values.items()}
        original_values = values.copy()
        active = 0
        history_index = -1
        self.status = ""
        try:
            self.curses.curs_set(1)
        except self.curses.error:
            pass
        while True:
            if not self._terminal_ready():
                self._minimum_size_message()
                key = self.screen.getch()
                if key == CTRL_X:
                    self._request_exit()
                if key == 27 and allow_cancel:
                    return False
                continue
            self._clear()
            self._add(0, 0, "New Jackett search", self.curses.A_BOLD)
            self._add(
                2,
                0,
                "Tab/Shift-Tab fields  Enter search  Esc back  Ctrl-X exit  Ctrl-C quit",
            )
            for index, field in enumerate(fields):
                row = 4 + index * 2
                prefix = ">" if index == active else " "
                label = FORM_FIELD_LABELS[field]
                self._add(row, 0, f"{prefix} {label:<{FORM_LABEL_WIDTH}}: {values[field]}")
            self._add(
                15,
                0,
                "Limit: result count; Timeout: seconds. ↑/k +1  ↓/j -1  blank Limit = no cap",
                self.curses.A_DIM,
            )
            if self.status:
                self._add(17, 0, self.status, self.curses.A_DIM)
            cursor_field = fields[active]
            cursor_column = FORM_LABEL_WIDTH + 4 + positions[cursor_field]
            self.screen.move(4 + active * 2, min(cursor_column, self.screen.getmaxyx()[1] - 1))
            self.screen.refresh()
            key = self.screen.getch()
            if key == CTRL_X:
                self._request_exit()
            if key == 27:
                if allow_cancel:
                    return False
                self.status = "Esc cancels dialogs. Press Ctrl-C to exit interactive mode."
                continue
            if key == 9:
                active = (active + 1) % len(fields)
                continue
            if key == self.curses.KEY_BTAB:
                active = (active - 1) % len(fields)
                continue
            if key in (10, 13, self.curses.KEY_ENTER):
                try:
                    limit = int(values["Limit"]) if values["Limit"] else None
                    timeout = int(values["Timeout"])
                    if limit is not None and limit < 0:
                        raise ValueError("Limit must be zero or greater.")
                    if timeout < 0:
                        raise ValueError("Timeout must be zero or greater.")
                    if not values["Query"].strip():
                        raise ValueError("Query is required.")
                except ValueError as error:
                    self.status = str(error)
                    self._show_message("Search form", self.status)
                    continue
                self.params = SearchParams(
                    values["Query"].strip(),
                    values["Sort"].strip() or "seeders",
                    limit,
                    timeout,
                    values["Filter"],
                )
                self._perform_search(record=True)
                return True
            if cursor_field in SELECTOR_FIELDS and key in (
                self.curses.KEY_LEFT,
                self.curses.KEY_UP,
                self.curses.KEY_RIGHT,
                self.curses.KEY_DOWN,
            ):
                step = -1 if key in (self.curses.KEY_LEFT, self.curses.KEY_UP) else 1
                options = SORT_OPTIONS if cursor_field == "Sort" else FILTER_OPTIONS
                values[cursor_field] = cycle_option(options, values[cursor_field], step)
                positions[cursor_field] = len(values[cursor_field])
                self.status = ""
                continue
            if cursor_field in NUMERIC_FIELDS and key in (
                self.curses.KEY_UP,
                ord("k"),
                self.curses.KEY_DOWN,
                ord("j"),
            ):
                delta = 1 if key in (self.curses.KEY_UP, ord("k")) else -1
                values[cursor_field] = adjust_numeric_value(values[cursor_field], delta)
                positions[cursor_field] = len(values[cursor_field])
                self.status = ""
                continue
            if cursor_field == "Query" and key == self.curses.KEY_UP and self.history:
                history_index = min(len(self.history) - 1, history_index + 1)
                entry = self.history[history_index]
                values.update(
                    {
                        "Query": entry.query,
                        "Sort": entry.sort,
                        "Limit": "" if entry.limit is None else str(entry.limit),
                        "Timeout": str(entry.timeout),
                        "Filter": entry.result_filter,
                    }
                )
                positions = {field: len(value) for field, value in values.items()}
                continue
            if cursor_field == "Query" and key == self.curses.KEY_DOWN and history_index >= 0:
                history_index -= 1
                if history_index >= 0:
                    entry = self.history[history_index]
                    values.update(
                        {
                            "Query": entry.query,
                            "Sort": entry.sort,
                            "Limit": "" if entry.limit is None else str(entry.limit),
                            "Timeout": str(entry.timeout),
                            "Filter": entry.result_filter,
                        }
                    )
                else:
                    values.update(original_values)
                positions = {field: len(value) for field, value in values.items()}
                continue
            if key == self.curses.KEY_LEFT:
                positions[cursor_field] = max(0, positions[cursor_field] - 1)
                continue
            if key == self.curses.KEY_RIGHT:
                positions[cursor_field] = min(
                    len(values[cursor_field]), positions[cursor_field] + 1
                )
                continue
            if key == self.curses.KEY_HOME:
                positions[cursor_field] = 0
                continue
            if key == self.curses.KEY_END:
                positions[cursor_field] = len(values[cursor_field])
                continue
            if key in (self.curses.KEY_BACKSPACE, 127, 8):
                position = positions[cursor_field]
                if position:
                    values[cursor_field] = (
                        values[cursor_field][: position - 1] + values[cursor_field][position:]
                    )
                    positions[cursor_field] -= 1
                continue
            if 32 <= key <= 126 and cursor_field not in SELECTOR_FIELDS:
                character = chr(key)
                if not accepts_field_character(cursor_field, character):
                    self.status = f"{cursor_field} accepts digits only."
                    continue
                position = positions[cursor_field]
                values[cursor_field] = (
                    values[cursor_field][:position] + character + values[cursor_field][position:]
                )
                positions[cursor_field] += 1
                self.status = ""

    def _show_message(
        self, title: str, message: str, prompt: str = "Press any key to continue."
    ) -> None:
        self._clear()
        self._add(0, 0, title, self.curses.A_BOLD)
        self._add(2, 0, message)
        self._add(4, 0, prompt, self.curses.A_DIM)
        self.screen.refresh()
        if self.screen.getch() == CTRL_X:
            self._request_exit()

    def _retry_or_return(self, title: str, message: str) -> bool:
        """Show an in-session failure and return whether the caller should retry."""
        self._clear()
        self._add(0, 0, title, self.curses.A_BOLD)
        self._add(2, 0, message)
        self._add(4, 0, "r retry  Esc return to results", self.curses.A_DIM)
        self.screen.refresh()
        while True:
            key = self.screen.getch()
            if key == CTRL_X:
                self._request_exit()
            if key in (27, ord("q")):
                return False
            if key == ord("r"):
                return True

    def _show_help(self) -> None:
        lines = [
            "Navigation",
            "  ↑/↓ or j/k       Select result",
            "  ←/→ or h/l       Select Magnet/Torrent",
            "  PageUp/PageDown   Move one page",
            "  Home/End or g/G   First/last result",
            "  Ctrl-U/Ctrl-D     Half-page up/down",
            "",
            "Actions",
            "  Enter             Choose client and act",
            "  c                 Copy selected URL",
            "  n                 New search",
            "  r                 Repeat current search",
            "  q                 Exit from results",
            "  Ctrl-X            Confirm exit from any screen",
            "  Ctrl-C            Exit immediately",
            "  Esc               Confirm cancel/return to the search form",
        ]
        self._clear()
        self._add(0, 0, "Interactive help", self.curses.A_BOLD)
        for index, line in enumerate(lines, 2):
            self._add(index, 0, line)
        self._add(len(lines) + 3, 0, "Press any key to return.", self.curses.A_DIM)
        self.screen.refresh()
        if self.screen.getch() == CTRL_X:
            self._request_exit()

    def _focused_url(self) -> Optional[str]:
        if not self.results:
            return None
        key = "MagnetUri" if self.focused_action == "magnet" else "Link"
        value = self.results[self.cursor_index].get(key)
        return str(value) if value else None

    def _copy_focused_url(self) -> None:
        url = self._focused_url()
        if url is None:
            self.status = "The selected result has no usable URL for this action."
            return
        success, message = copy_to_clipboard(url)
        self.status = message
        if not success:
            self._show_message("Copy URL", message)

    def _choose(
        self, title: str, options: Sequence[Tuple[str, str]], selected: Optional[str]
    ) -> Optional[str]:
        if not options:
            self._show_message(title, "No supported client is available.")
            return None
        keys = [key for key, _ in options]
        index = keys.index(selected) if selected in keys else 0
        while True:
            self._clear()
            self._add(0, 0, title, self.curses.A_BOLD)
            for offset, (_, label) in enumerate(options, 2):
                attribute = self.curses.A_REVERSE if offset - 2 == index else 0
                self._add(offset, 2, label, attribute)
            self._add(len(options) + 3, 0, "Enter select  Esc cancel", self.curses.A_DIM)
            self.screen.refresh()
            key = self.screen.getch()
            if key == CTRL_X:
                self._request_exit()
            if key in (27, ord("q")):
                return None
            if key in (self.curses.KEY_UP, ord("k")):
                index = (index - 1) % len(options)
            elif key in (self.curses.KEY_DOWN, ord("j")):
                index = (index + 1) % len(options)
            elif key in (10, 13, self.curses.KEY_ENTER):
                return options[index][0]

    def _confirm(self, client_label: str, folder_path: Optional[str]) -> bool:
        title = str(self.results[self.cursor_index].get("Title") or "Untitled")
        lines = [f"Use {self.focused_action} for:", _truncate(title, 80), f"Client: {client_label}"]
        if folder_path:
            lines.append(f"Destination: {folder_path}")
        self._clear()
        self._add(0, 0, "Confirm action", self.curses.A_BOLD)
        for index, line in enumerate(lines, 2):
            self._add(index, 0, line)
        self._add(len(lines) + 3, 0, "Enter/y confirm  Esc cancel", self.curses.A_DIM)
        self.screen.refresh()
        while True:
            key = self.screen.getch()
            if key == CTRL_X:
                self._request_exit()
            if key in (10, 13, self.curses.KEY_ENTER, ord("y"), ord("Y")):
                return True
            if key in (27, ord("q"), ord("n"), ord("N")):
                return False

    def _confirm_search_transition(self, title: str, message: str) -> bool:
        """Ask before an Esc key discards the active search view or worker."""
        while True:
            self._clear()
            self._add(0, 0, title, self.curses.A_BOLD)
            self._add(2, 0, message)
            self._add(4, 0, "Enter/y confirm  Esc/n continue", self.curses.A_DIM)
            self.screen.timeout(-1)
            self.screen.refresh()
            key = self.screen.getch()
            if key == CTRL_X:
                self._request_exit()
            if key in (10, 13, self.curses.KEY_ENTER, ord("y"), ord("Y")):
                return True
            if key in (27, ord("q"), ord("n"), ord("N")):
                return False

    def _confirm_exit(self) -> bool:
        """Ask before Ctrl-X leaves the interactive session from an editable view."""
        self._clear()
        self._add(0, 0, "Exit interactive mode?", self.curses.A_BOLD)
        self._add(2, 0, "The current search view will close.")
        self._add(4, 0, "Enter/y or Ctrl-X exit  Esc/n continue", self.curses.A_DIM)
        self.screen.timeout(-1)
        self.screen.refresh()
        while True:
            key = self.screen.getch()
            if key in (CTRL_X, 10, 13, self.curses.KEY_ENTER, ord("y"), ord("Y")):
                return True
            if key in (27, ord("q"), ord("n"), ord("N")):
                return False

    def _request_exit(self) -> None:
        """Unwind the active UI view only after a confirmed Ctrl-X request."""
        if self._confirm_exit():
            raise ExitInteractiveMode()

    def _activate_focused_action(self) -> None:
        url = self._focused_url()
        if url is None:
            self.status = "The selected result has no usable URL for this action."
            return
        clients = available_clients()
        if self.focused_action == "torrent":
            # Jackett's Link can be its authenticated, private /dl/ proxy URL.
            # A remote put.io transfer cannot reach that endpoint. Torrent-payload
            # upload is a separate future adapter, so only magnets offer put.io.
            clients = [(key, label) for key, label in clients if key != "putio"]
        selected = self._choose("Choose application", clients, self.preferences.last_client)
        if selected is None:
            return
        if selected == "putio":
            self._activate_putio(url)
        else:
            self._activate_default(url)

    def _activate_default(self, url: str) -> None:
        label = "System default application"
        if not self._confirm(label, None):
            return
        command = "open" if sys.platform == "darwin" else "xdg-open"
        while True:
            try:
                completed = subprocess.run(
                    [command, url], capture_output=True, text=True, check=False
                )
            except OSError as error:
                message = str(error)
            else:
                if completed.returncode == 0:
                    break
                message = completed.stderr.strip() or "Could not open the URL."
            if not self._retry_or_return("Open failed", message):
                return
        preference_notice = self._persist_client("default")
        self.status = "Opened with the system default application." + preference_notice
        self._show_message("Action complete", self.status)

    def _run_cancellable_command(
        self,
        command: Sequence[str],
        progress: str,
        cancel_title: str,
        cancel_message: str,
    ) -> subprocess.CompletedProcess:
        """Run a command without a shell while allowing confirmed cancellation."""
        self._draw_loading(progress)
        with tempfile.TemporaryFile(
            mode="w+t", encoding="utf-8"
        ) as stdout_file, tempfile.TemporaryFile(mode="w+t", encoding="utf-8") as stderr_file:
            process = subprocess.Popen(command, stdout=stdout_file, stderr=stderr_file, text=True)
            try:
                while process.poll() is None:
                    self.screen.timeout(100)
                    key = self.screen.getch()
                    if key == CTRL_X:
                        if self._confirm_exit():
                            self._stop_subprocess(process)
                            raise ExitInteractiveMode()
                        self._draw_loading(progress)
                        continue
                    if key == 27:
                        if self._confirm_search_transition(cancel_title, cancel_message):
                            self._stop_subprocess(process)
                            raise CancelledError()
                        self._draw_loading(progress)
                    time.sleep(0.02)
            except KeyboardInterrupt:
                self._stop_subprocess(process)
                raise
            finally:
                self.screen.timeout(-1)
            stdout_file.seek(0)
            stderr_file.seek(0)
            stdout = stdout_file.read()
            stderr = stderr_file.read().strip()
        return subprocess.CompletedProcess(
            list(command),
            process.returncode if process.returncode is not None else 1,
            stdout,
            stderr,
        )

    def _run_folder_command(self, command: Sequence[str], progress: str) -> Dict[str, Any]:
        """Run a put.io folder query and decode its JSON response."""
        completed = self._run_cancellable_command(
            command,
            progress,
            "Cancel put.io folder discovery?",
            "This stops the current folder lookup.",
        )
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr or "put.io folder lookup failed.")
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as error:
            raise RuntimeError("put.io returned invalid folder data.") from error
        if not isinstance(payload, dict):
            raise RuntimeError("put.io returned an unexpected folder response.")
        return payload

    @staticmethod
    def _stop_subprocess(process: subprocess.Popen) -> None:
        """Terminate and reap a cancellable child process exactly once."""
        if process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()

    def _discover_putio_folders(self) -> List[PutioFolder]:
        folders = [PutioFolder(0, "Root")]
        queue = [(0, "")]
        visited = {0}
        while queue:
            parent_id, parent_path = queue.pop(0)
            payload = self._run_folder_command(
                [
                    "putio",
                    "files",
                    "list",
                    "--file-type",
                    "FOLDER",
                    "--parent-id",
                    str(parent_id),
                    "--page-all",
                    "--output",
                    "json",
                ],
                f"Loading put.io folders… scanning {parent_path or 'Root'}",
            )
            for folder in parse_putio_folders(payload, parent_path):
                if folder.id in visited:
                    continue
                visited.add(folder.id)
                folders.append(folder)
                queue.append((folder.id, folder.path))
        return [folders[0]] + sorted(folders[1:], key=lambda folder: folder.path.casefold())

    def _choose_folder(self, folders: Sequence[PutioFolder]) -> Optional[PutioFolder]:
        filter_text = ""
        initial = next(
            (
                index
                for index, folder in enumerate(folders)
                if folder.id == self.preferences.putio_last_folder_id
            ),
            0,
        )
        selected_id = folders[initial].id
        while True:
            filtered = [
                folder
                for folder in folders
                if folder.path == "Root" or filter_text.casefold() in folder.path.casefold()
            ]
            if not filtered:
                selected_id = 0
            index = next((i for i, folder in enumerate(filtered) if folder.id == selected_id), 0)
            if filtered:
                selected_id = filtered[index].id
            self._clear()
            height, width = self.screen.getmaxyx()
            self._add(0, 0, "Choose put.io destination", self.curses.A_BOLD)
            self._add(1, 0, f"Filter: {filter_text or '(type to filter)'}", self.curses.A_DIM)
            visible = max(1, height - 6)
            top = max(0, min(index - visible // 2, max(0, len(filtered) - visible)))
            for offset, folder in enumerate(filtered[top : top + visible], 3):
                attribute = self.curses.A_REVERSE if folder.id == selected_id else 0
                self._add(offset, 2, _middle_truncate(folder.path, width - 4), attribute)
            selected = next((folder for folder in folders if folder.id == selected_id), None)
            if selected:
                self._add(height - 2, 0, f"Selected: {selected.path}", self.curses.A_BOLD)
            self._add(
                height - 1,
                0,
                "↑↓ rows  PgUp/PgDn  Home/End  Enter select  Esc cancel  Ctrl-X exit",
                self.curses.A_DIM,
            )
            self.screen.refresh()
            key = self.screen.getch()
            if key == CTRL_X:
                self._request_exit()
            if key == 27:
                return None
            if key in (self.curses.KEY_BACKSPACE, 127, 8):
                filter_text = filter_text[:-1]
                continue
            if 32 <= key <= 126:
                filter_text += chr(key)
                continue
            if not filtered:
                continue
            if key == self.curses.KEY_UP:
                selected_id = filtered[(index - 1) % len(filtered)].id
            elif key == self.curses.KEY_DOWN:
                selected_id = filtered[(index + 1) % len(filtered)].id
            elif key == self.curses.KEY_PPAGE:
                selected_id = filtered[max(0, index - visible)].id
            elif key == self.curses.KEY_NPAGE:
                selected_id = filtered[min(len(filtered) - 1, index + visible)].id
            elif key == self.curses.KEY_HOME:
                selected_id = filtered[0].id
            elif key == self.curses.KEY_END:
                selected_id = filtered[-1].id
            elif key in (10, 13, self.curses.KEY_ENTER):
                return filtered[index]

    def _activate_putio(self, url: str) -> None:
        while True:
            try:
                folders = self._discover_putio_folders()
            except CancelledError:
                self.status = "put.io folder discovery cancelled."
                return
            except (OSError, RuntimeError) as error:
                if self._retry_or_return("put.io error", str(error)):
                    continue
                return
            break
        folder = self._choose_folder(folders)
        if folder is None or not self._confirm("put.io", folder.path):
            return
        while True:
            try:
                completed = self._run_cancellable_command(
                    putio_add_command(url, folder.id),
                    "Creating put.io transfer…",
                    "Cancel put.io transfer creation?",
                    "This stops the local put.io command. The transfer may already exist remotely.",
                )
            except CancelledError:
                self.status = (
                    "put.io transfer creation cancelled. Check put.io transfers; "
                    "the request may already have been accepted."
                )
                return
            except OSError as error:
                message = str(error)
            else:
                if completed.returncode == 0:
                    break
                message = completed.stderr.strip() or "Transfer was rejected."
            if not self._retry_or_return("put.io error", message):
                return
        try:
            response = json.loads(completed.stdout)
        except json.JSONDecodeError:
            response = {}
        preference_notice = self._persist_client("putio") + self._persist_putio_folder(folder.id)
        transfer_id = _transfer_id(response) if isinstance(response, dict) else None
        if transfer_id is None:
            self.status = f"Transfer created in {folder.path}." + preference_notice
            self._show_message("put.io transfer created", self.status)
            return
        self._post_submit_cancel(transfer_id, folder.path, preference_notice)

    def _post_submit_cancel(
        self, transfer_id: int, folder_path: str, preference_notice: str = ""
    ) -> None:
        self._clear()
        self._add(0, 0, "put.io transfer created", self.curses.A_BOLD)
        self._add(2, 0, f"Destination: {folder_path}")
        self._add(3, 0, f"Transfer ID: {transfer_id}")
        self._add(5, 0, "c cancel transfer  Enter continue", self.curses.A_DIM)
        self.screen.refresh()
        while True:
            key = self.screen.getch()
            if key == CTRL_X:
                self._request_exit()
            if key in (10, 13, self.curses.KEY_ENTER, 27):
                self.status = f"Transfer created in {folder_path}." + preference_notice
                return
            if key == ord("c"):
                while True:
                    try:
                        completed = self._run_cancellable_command(
                            putio_cancel_command(transfer_id),
                            "Cancelling put.io transfer…",
                            "Stop put.io transfer cancellation?",
                            (
                                "This stops the local put.io command. The cancellation may already "
                                "have been accepted remotely."
                            ),
                        )
                    except CancelledError:
                        self.status = (
                            f"Transfer {transfer_id} cancellation command stopped. "
                            "Check put.io transfers; the cancellation may already have been "
                            "accepted." + preference_notice
                        )
                        return
                    except OSError as error:
                        message = str(error)
                    else:
                        if completed.returncode == 0:
                            self.status = f"Transfer {transfer_id} cancelled." + preference_notice
                            self._show_message("put.io transfer", self.status)
                            return
                        message = completed.stderr.strip() or "Could not cancel the transfer."
                    if not self._retry_or_return("put.io cancellation failed", message):
                        self.status = message
                        return

    def _persist_client(self, client: str) -> str:
        self.preferences.last_client = client
        return self._persist_preferences({"interactive": {"last_client": client}})

    def _persist_putio_folder(self, folder_id: int) -> str:
        self.preferences.putio_last_folder_id = folder_id
        return self._persist_preferences(
            {"interactive.clients.putio": {"last_folder_id": folder_id}},
        )

    def _persist_preferences(self, updates: Dict[str, Dict[str, Any]]) -> str:
        """Keep completed actions successful when optional preference saving fails."""
        try:
            update_toml_sections(self.config_path, updates)
        except OSError as error:
            return f" Preference was not saved: {error}."
        return ""
