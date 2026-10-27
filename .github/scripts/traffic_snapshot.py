"""Snapshot repository traffic, stars and PyPI downloads into CSV files.

GitHub only keeps 14 days of traffic data, so after a launch (Show HN, Reddit,
a blog post) you lose the answer to "where did those stars come from?" unless
you save it. This script merges each run into CSVs that grow over time:

    stars.csv       date, stars, forks, watchers, open_issues
    views.csv       date, views, unique_visitors      (daily, from GitHub traffic)
    clones.csv      date, clones, unique_cloners      (daily, from GitHub traffic)
    referrers.csv   snapshot_date, referrer, views, uniques   (14-day window)
    paths.csv       snapshot_date, path, views, uniques       (14-day window)
    pypi.csv        date, downloads                    (daily, from pypistats.org)

It also writes a Markdown report to $GITHUB_STEP_SUMMARY. Standard library only.

Environment:
    GITHUB_REPOSITORY   owner/repo
    GITHUB_TOKEN        token for the repo endpoints (the workflow token is enough)
    TRAFFIC_TOKEN       token that can read traffic (fine-grained PAT with
                        "Administration: Read-only" on this repo). Optional:
                        without it only stars and PyPI downloads are recorded.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path
from typing import Any

API = "https://api.github.com"


def get_json(url: str, token: str | None = None) -> Any:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "portpilot-traffic"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_rows(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def upsert(path: Path, fields: list[str], key: str, new: list[dict[str, Any]]) -> None:
    """Merge rows by `key`; newer values win (today's partial count gets corrected)."""
    rows = {r[key]: r for r in read_rows(path)}
    for r in new:
        rows[str(r[key])] = {k: str(v) for k, v in r.items()}
    write_rows(path, fields, [rows[k] for k in sorted(rows)])


def replace_snapshot(path: Path, fields: list[str], today: str, new: list[dict[str, Any]]) -> None:
    """Keep earlier snapshots, replace today's (so re-runs don't duplicate)."""
    rows = [r for r in read_rows(path) if r["snapshot_date"] != today]
    rows += [{"snapshot_date": today, **r} for r in new]
    write_rows(path, fields, rows)


def daily(items: list[dict[str, Any]], count_key: str, unique_key: str) -> list[dict[str, Any]]:
    return [
        {"date": i["timestamp"][:10], count_key: i["count"], unique_key: i["uniques"]}
        for i in items
    ]


def collect(out: Path, repo: str, token: str | None, traffic_token: str | None) -> dict[str, Any]:
    today = date.today().isoformat()
    report: dict[str, Any] = {"today": today, "traffic": False}

    meta = get_json(f"{API}/repos/{repo}", token)
    star_row = {
        "date": today,
        "stars": meta["stargazers_count"],
        "forks": meta["forks_count"],
        "watchers": meta["subscribers_count"],
        "open_issues": meta["open_issues_count"],
    }
    upsert(out / "stars.csv", list(star_row), "date", [star_row])

    if traffic_token:
        try:
            views = get_json(f"{API}/repos/{repo}/traffic/views?per=day", traffic_token)
            clones = get_json(f"{API}/repos/{repo}/traffic/clones?per=day", traffic_token)
            refs = get_json(f"{API}/repos/{repo}/traffic/popular/referrers", traffic_token)
            paths = get_json(f"{API}/repos/{repo}/traffic/popular/paths", traffic_token)
        except urllib.error.HTTPError as e:
            print(f"::warning::Traffic API returned HTTP {e.code}; check TRAFFIC_TOKEN permissions")
        else:
            upsert(
                out / "views.csv",
                ["date", "views", "unique_visitors"],
                "date",
                daily(views["views"], "views", "unique_visitors"),
            )
            upsert(
                out / "clones.csv",
                ["date", "clones", "unique_cloners"],
                "date",
                daily(clones["clones"], "clones", "unique_cloners"),
            )
            ref_rows = [
                {"referrer": r["referrer"], "views": r["count"], "uniques": r["uniques"]}
                for r in refs
            ]
            replace_snapshot(
                out / "referrers.csv",
                ["snapshot_date", "referrer", "views", "uniques"],
                today,
                ref_rows,
            )
            replace_snapshot(
                out / "paths.csv",
                ["snapshot_date", "path", "views", "uniques"],
                today,
                [{"path": p["path"], "views": p["count"], "uniques": p["uniques"]} for p in paths],
            )
            report.update(traffic=True, referrers=ref_rows)
    else:
        print("::notice::TRAFFIC_TOKEN not set; recording stars and PyPI downloads only")

    try:
        pypi = get_json("https://pypistats.org/api/packages/portpilot/overall?mirrors=false")
        rows = [
            {"date": d["date"], "downloads": d["downloads"]}
            for d in pypi["data"]
            if d.get("category") == "without_mirrors"
        ]
        upsert(out / "pypi.csv", ["date", "downloads"], "date", rows)
    except (urllib.error.URLError, KeyError, json.JSONDecodeError) as e:
        print(f"::warning::PyPI stats unavailable: {e}")

    return report


def week_sum(path: Path, column: str, end: date) -> tuple[int, int]:
    """Sum of `column` over the last 7 days and the 7 days before that."""
    rows = {r["date"]: int(r[column]) for r in read_rows(path)}

    def window(offset: int) -> int:
        days = (end - timedelta(days=offset + i) for i in range(7))
        return sum(rows.get(d.isoformat(), 0) for d in days)

    return window(0), window(7)


def star_delta(path: Path, end: date, days: int) -> int | None:
    rows = {r["date"]: int(r["stars"]) for r in read_rows(path)}
    now = rows.get(end.isoformat())
    then = rows.get((end - timedelta(days=days)).isoformat())
    return None if now is None or then is None else now - then


def markdown_report(out: Path, report: dict[str, Any]) -> str:
    end = date.fromisoformat(report["today"])
    stars = read_rows(out / "stars.csv")[-1]
    lines = [f"## 📈 PortPilot visibility — {report['today']}", ""]

    d7, d30 = star_delta(out / "stars.csv", end, 7), star_delta(out / "stars.csv", end, 30)
    deltas = ", ".join(
        f"{label} {'+' if v >= 0 else ''}{v}"
        for label, v in (("7d", d7), ("30d", d30))
        if v is not None
    )
    lines.append(
        f"**⭐ {stars['stars']} stars** · {stars['forks']} forks"
        + (f" ({deltas})" if deltas else "")
    )
    lines.append("")

    rows = [("Metric", "Last 7 days", "Previous 7 days")]
    if report["traffic"]:
        rows.append(("Views", *map(str, week_sum(out / "views.csv", "views", end))))
        rows.append(
            ("Unique visitors", *map(str, week_sum(out / "views.csv", "unique_visitors", end)))
        )
        rows.append(("Clones", *map(str, week_sum(out / "clones.csv", "clones", end))))
    if (out / "pypi.csv").exists():
        # pypistats lags a day behind, so compare windows ending yesterday
        rows.append(
            (
                "PyPI downloads",
                *map(str, week_sum(out / "pypi.csv", "downloads", end - timedelta(days=1))),
            )
        )
    if len(rows) > 1:
        lines += [f"| {' | '.join(r)} |" for r in rows[:1]]
        lines.append("|---|---:|---:|")
        lines += [f"| {' | '.join(r)} |" for r in rows[1:]]
        lines.append("")

    refs = report.get("referrers") or []
    if refs:
        lines += [
            "**Top referrers (14 days)**",
            "",
            "| Referrer | Views | Uniques |",
            "|---|---:|---:|",
        ]
        lines += [f"| {r['referrer']} | {r['views']} | {r['uniques']} |" for r in refs[:10]]
        lines.append("")
    elif not report["traffic"]:
        lines.append("_Add a `TRAFFIC_TOKEN` secret to also record views, clones and referrers._")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True, help="directory for the CSV files")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    report = collect(
        args.out,
        os.environ["GITHUB_REPOSITORY"],
        os.environ.get("GITHUB_TOKEN"),
        os.environ.get("TRAFFIC_TOKEN") or None,
    )
    md = markdown_report(args.out, report)
    (args.out / "README.md").write_text(
        md + "\nUpdated daily by `.github/workflows/traffic.yml` on the main branch.\n",
        encoding="utf-8",
    )
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(summary, "a", encoding="utf-8") as f:
            f.write(md)
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
