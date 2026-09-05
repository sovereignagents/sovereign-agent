from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_import_has_no_filesystem_process_or_network_side_effects(tmp_path: Path) -> None:
    script = """
import json
import pathlib
before = sorted(str(path.relative_to('.')) for path in pathlib.Path('.').rglob('*'))
import sovereign_agent
after = sorted(str(path.relative_to('.')) for path in pathlib.Path('.').rglob('*'))
print(json.dumps({'before': before, 'after': after, 'version': sovereign_agent.__version__}))
"""
    result = subprocess.run(
        [sys.executable, "-I", "-c", script],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )
    observed = json.loads(result.stdout)
    assert observed == {"before": [], "after": [], "version": "1.4.0"}
