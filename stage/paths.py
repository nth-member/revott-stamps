"""Local paths, read from the untracked .paths.json so that none is written into the published code."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_P = json.loads((ROOT / ".paths.json").read_text())
HISTORY = Path(_P["history"]).expanduser()      # the feed history: items.jsonl.gz, coverage.jsonl.gz
JOMO = Path(_P["jomo"]).expanduser()            # the JOMO SFO-WAM checkout: its snapshots and catalogue
REVOTT = Path(_P["revott"]).expanduser()        # REVOTT, for the 400 keys
