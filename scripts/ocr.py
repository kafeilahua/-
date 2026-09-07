"""Local PaddleOCR API client; no external cloud uploads.
uv run python -m scripts.ocr submit book.pdf
uv run python -m scripts.ocr status JOB_ID
uv run python -m scripts.ocr download JOB_ID
"""

import argparse
import json
import os
from pathlib import Path

import httpx


def main():
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=["submit", "status", "download", "retry", "cancel"])
    p.add_argument("target")
    p.add_argument("--url", default=os.getenv("SC200_OCR_URL", "http://192.168.1.10:8000"))
    p.add_argument("--output", default="data/ocr-result.json")
    a = p.parse_args()
    with httpx.Client(base_url=a.url, timeout=120) as c:
        if a.action == "submit":
            with open(a.target, "rb") as f:
                r = c.post(
                    "/api/ocr",
                    files={"file": (Path(a.target).name, f, "application/pdf")},
                    data={"dpi": "200"},
                )
        elif a.action in ("retry", "cancel"):
            r = c.post(f"/api/jobs/{a.target}/{a.action}")
        elif a.action == "download":
            status = c.get(f"/api/jobs/{a.target}")
            status.raise_for_status()
            if status.json()["status"] != "completed":
                raise SystemExit("任务尚未完成：" + status.text)
            r = c.get(f"/api/jobs/{a.target}/result", params={"format": "json"})
            r.raise_for_status()
            Path(a.output).write_text(json.dumps(r.json(), ensure_ascii=False, indent=2))
            print(a.output)
            return
        else:
            r = c.get(f"/api/jobs/{a.target}")
        r.raise_for_status()
        print(json.dumps(r.json(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
