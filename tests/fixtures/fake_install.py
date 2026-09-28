#!/usr/bin/env python3
"""Fail the second install invocation during an upgrade test."""

import os
import sys
from pathlib import Path

counter_path = Path(os.environ["INSTALL_COUNTER"])
count = int(counter_path.read_text(encoding="utf-8")) if counter_path.exists() else 0
count += 1
counter_path.write_text(str(count) + "\n", encoding="utf-8")
if count == 2:
    sys.exit(1)
real_install = os.environ["REAL_INSTALL"]
os.execv(real_install, [real_install] + sys.argv[1:])
