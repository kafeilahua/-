"""Consistent SQLite backup, including data currently held in WAL files."""

import argparse
import sqlite3
from pathlib import Path

from backend.db import DATA

p = argparse.ArgumentParser()
p.add_argument("destination")
a = p.parse_args()
dest = Path(a.destination)
if dest.exists():
    raise SystemExit("目标文件已存在，请使用新文件名。")
source = DATA / "study.db"
if not source.is_file():
    raise SystemExit("数据库不存在，请先运行应用。")
with sqlite3.connect(f"file:{source}?mode=ro", uri=True) as src, sqlite3.connect(dest) as dst:
    src.backup(dst)
print(dest.resolve())
