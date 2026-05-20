"""Trim log files older than 7 days. Called from run_daily.bat on every invocation."""
import re
from datetime import datetime, timedelta
from pathlib import Path

LOG_DIR = Path(__file__).parent
CUTOFF = datetime.now() - timedelta(days=7)


def trim_autologin_log(path: Path):
    """log_autologin.txt: lines formatted as [YYYY-MM-DD HH:MM:SS] ..."""
    if not path.exists():
        return
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
    result = []
    keep = True
    pat = re.compile(r'^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]')
    for line in lines:
        m = pat.match(line)
        if m:
            ts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
            keep = ts >= CUTOFF
        if keep:
            result.append(line)
    path.write_text("".join(result), encoding="utf-8")


def trim_session_log(path: Path):
    """log_signal.txt / log_order.txt: sessions delimited by ===... lines, contain 実行時刻: YYYY-MM-DD."""
    if not path.exists():
        return
    content = path.read_text(encoding="utf-8", errors="replace")
    # Split at lines that start with 10+ '=' (lookahead keeps the delimiter with its block)
    blocks = re.split(r'(?m)(?=^={10,})', content)
    pat = re.compile(r'実行時刻[：:]\s*(\d{4}-\d{2}-\d{2})')
    result = []
    for block in blocks:
        m = pat.search(block)
        if m:
            ts = datetime.strptime(m.group(1), "%Y-%m-%d")
            if ts < CUTOFF:
                continue
        result.append(block)
    path.write_text("".join(result), encoding="utf-8")


if __name__ == "__main__":
    for name, func in [
        ("log_autologin.txt", trim_autologin_log),
        ("log_signal.txt", trim_session_log),
        ("log_order.txt", trim_session_log),
    ]:
        func(LOG_DIR / name)
