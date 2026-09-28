#!/usr/bin/env python3
"""Record Docker invocations made by installation tests."""

import os
import sys
from pathlib import Path

with Path(os.environ["DOCKER_LOG"]).open("a", encoding="utf-8") as output:
    output.write(" ".join(sys.argv[1:]) + "\n")
