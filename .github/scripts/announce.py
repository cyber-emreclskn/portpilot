"""Announce a PortPilot release on Bluesky and Mastodon.

Builds a short post from the release notes (the first "Features" bullets that
release-please writes) and sends it to every network whose credentials are set.
Networks without credentials are skipped, so the script is safe to run with
none configured. Standard library only.

Usage:
    python .github/scripts/announce.py --tag v0.3.0 --notes notes.md [--dry-run]
    python .github/scripts/announce.py --tag v0.3.0 --message "custom text"

Environment:
    BLUESKY_HANDLE, BLUESKY_APP_PASSWORD   Bluesky account + app password
    MASTODON_INSTANCE, MASTODON_TOKEN      e.g. https://fosstodon.org + access token
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

REPO_URL = "https://github.com/cyber-emreclskn/portpilot"
HASHTAGS = ["python", "cli", "tui", "devtools"]
BLUESKY_LIMIT = 300  # graphemes; we count code points, which is stricter for emoji
MASTODON_LIMIT = 500


def highlights(notes: str, limit: int = 2) -> list[str]:
    """Return up to `limit` cleaned bullets from the Features section, falling back
    to Bug Fixes. release-please bullets look like:
    * **tui:** add sort by memory ([#12](...)) ([abc1234](...))
    """
    sections: dict[str, list[str]] = {}
    current = None
    for line in notes.splitlines():
        heading = re.match(r"^#{2,4}\s+(.*)", line)
        if heading:
            current = heading.group(1).strip().lower()
            sections.setdefault(current, [])
            continue
        bullet = re.match(r"^\s*[*-]\s+(.*)", line)
        if bullet and current is not None:
            sections[current].append(clean_bullet(bullet.group(1)))

    for wanted in ("features", "bug fixes"):
        for name, items in sections.items():
            if name.startswith(wanted) and items:
                return [i for i in items if i][:limit]
    return []


def clean_bullet(text: str) -> str:
    text = re.sub(r"\s*\(\[[^\]]*\]\([^)]*\)\)", "", text)  # ([#12](url)) / ([sha](url))
    text = re.sub(r"\*\*([^*]+):\*\*\s*", "", text)  # **scope:** prefix
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)  # remaining links
    text = text.replace("`", "").strip()
    return text[:1].upper() + text[1:]


def build_post(tag: str, notes: str, message: str | None, limit: int) -> str:
    release_url = f"{REPO_URL}/releases/tag/{tag}"
    tags = " ".join(f"#{t}" for t in HASHTAGS)
    if message:
        head = message.strip()
    else:
        head = f"🛫 PortPilot {tag} is out: find and kill whatever is squatting on your dev ports."
        items = highlights(notes)
        if items:
            head += "\n\n" + "\n".join(f"• {i}" for i in items)
        head += "\n\nTry it without installing: uvx portpilot"
    tail = f"\n\n{release_url}\n{tags}"
    budget = limit - len(tail)
    if len(head) > budget:
        head = head[: budget - 1].rstrip() + "…"
    return head + tail


def utf8_span(text: str, part: str) -> tuple[int, int]:
    start = text.rindex(part)  # links and hashtags live in the tail of the post
    byte_start = len(text[:start].encode())
    return byte_start, byte_start + len(part.encode())


def bluesky_facets(text: str) -> list[dict]:
    facets = []
    for m in re.finditer(r"https://\S+", text):
        start, end = utf8_span(text, m.group(0))
        facets.append(
            {
                "index": {"byteStart": start, "byteEnd": end},
                "features": [{"$type": "app.bsky.richtext.facet#link", "uri": m.group(0)}],
            }
        )
    for t in HASHTAGS:
        start, end = utf8_span(text, f"#{t}")
        facets.append(
            {
                "index": {"byteStart": start, "byteEnd": end},
                "features": [{"$type": "app.bsky.richtext.facet#tag", "tag": t}],
            }
        )
    return facets


def http_json(url: str, payload: dict, headers: dict[str, str] | None = None) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{url} -> HTTP {e.code}: {e.read().decode(errors='replace')}") from e


def post_bluesky(text: str, tag: str) -> str:
    handle = os.environ["BLUESKY_HANDLE"]
    session = http_json(
        "https://bsky.social/xrpc/com.atproto.server.createSession",
        {"identifier": handle, "password": os.environ["BLUESKY_APP_PASSWORD"]},
    )
    record = {
        "$type": "app.bsky.feed.post",
        "text": text,
        "facets": bluesky_facets(text),
        "createdAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "langs": ["en"],
        "embed": {
            "$type": "app.bsky.embed.external",
            "external": {
                "uri": REPO_URL,
                "title": f"PortPilot {tag}",
                "description": "Interactive TUI + CLI to list, inspect and kill processes "
                "listening on ports. Linux, macOS, Windows.",
            },
        },
    }
    result = http_json(
        "https://bsky.social/xrpc/com.atproto.repo.createRecord",
        {"repo": session["did"], "collection": "app.bsky.feed.post", "record": record},
        {"Authorization": f"Bearer {session['accessJwt']}"},
    )
    rkey = result["uri"].rsplit("/", 1)[-1]
    return f"https://bsky.app/profile/{handle}/post/{rkey}"


def post_mastodon(text: str, tag: str) -> str:
    instance = os.environ["MASTODON_INSTANCE"].rstrip("/")
    result = http_json(
        f"{instance}/api/v1/statuses",
        {"status": text, "visibility": "public", "language": "en"},
        {
            "Authorization": f"Bearer {os.environ['MASTODON_TOKEN']}",
            "Idempotency-Key": f"portpilot-{tag}",  # re-runs won't double-post
        },
    )
    return str(result.get("url", ""))


NETWORKS = {
    "Bluesky": (("BLUESKY_HANDLE", "BLUESKY_APP_PASSWORD"), BLUESKY_LIMIT, post_bluesky),
    "Mastodon": (("MASTODON_INSTANCE", "MASTODON_TOKEN"), MASTODON_LIMIT, post_mastodon),
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tag", required=True)
    parser.add_argument("--notes", help="file with the release notes (markdown)")
    parser.add_argument("--message", help="custom text instead of the generated one")
    parser.add_argument("--dry-run", action="store_true", help="print the posts, send nothing")
    args = parser.parse_args()

    notes = ""
    if args.notes and os.path.exists(args.notes):
        with open(args.notes, encoding="utf-8") as f:
            notes = f.read()

    failures = 0
    summary = []
    for name, (env_vars, limit, send) in NETWORKS.items():
        text = build_post(args.tag, notes, args.message, limit)
        if args.dry_run:
            print(f"--- {name} ({len(text)}/{limit}) ---\n{text}\n")
            continue
        missing = [v for v in env_vars if not os.environ.get(v)]
        if missing:
            print(f"{name}: skipped (set {', '.join(missing)} to enable)")
            summary.append(f"- {name}: skipped, no credentials")
            continue
        try:
            url = send(text, args.tag)
            print(f"{name}: posted {url}")
            summary.append(f"- {name}: [posted]({url})")
        except Exception as e:  # keep going so one network can't block the other
            failures += 1
            print(f"::error::{name}: {e}")
            summary.append(f"- {name}: failed ({e})")

    step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary and summary:
        with open(step_summary, "a", encoding="utf-8") as f:
            f.write(f"### Release announcement for {args.tag}\n\n" + "\n".join(summary) + "\n")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
