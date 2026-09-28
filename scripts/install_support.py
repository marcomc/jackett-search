"""Small Python helpers used by the Makefile during installation."""

import json
import sys
from pathlib import Path


def configure_jackett(config_path):
    """Point Docker Jackett at the shared FlareSolverr service."""
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["FlareSolverrUrl"] = "http://flaresolverr:8191"
    config["LocalBindAddress"] = "0.0.0.0"
    config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")


def main(arguments):
    if arguments == ["check-python"]:
        return 0 if sys.version_info >= (3, 8) else 1
    if len(arguments) == 2 and arguments[0] == "configure-jackett":
        configure_jackett(Path(arguments[1]))
        return 0
    print("Usage: install_support.py check-python | configure-jackett PATH", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
