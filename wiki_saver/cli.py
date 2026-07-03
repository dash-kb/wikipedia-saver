from __future__ import annotations

import argparse
import json
from pathlib import Path

from .saver import GitBackedWikiArchive, WikiSaverError, default_repo_path
from .server import serve


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Save Wikipedia pages into a local git archive.")
    parser.add_argument(
        "--repo",
        default=str(default_repo_path()),
        help="Path to the saved-page git repo. Defaults to ../local-wiki.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    save = subparsers.add_parser("save", help="Save one Wikipedia URL now.")
    save.add_argument("url")

    subparsers.add_parser("init", help="Initialize the saved-page git repo.")

    update_all = subparsers.add_parser("update-all", help="Refresh every saved page and commit any changes.")
    update_all.add_argument("--force", action="store_true", help="Refresh now even if the interval has not elapsed.")

    settings = subparsers.add_parser("settings", help="Show or update refresh settings.")
    settings.add_argument("--refresh-interval-days", type=int)

    server = subparsers.add_parser("serve", help="Run the local HTTP server for the browser extension.")
    server.add_argument("--host", default="127.0.0.1")
    server.add_argument("--port", type=int, default=8765)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    repo = Path(args.repo).expanduser()

    try:
        if args.command == "serve":
            serve(args.host, args.port, repo)
            return 0

        archive = GitBackedWikiArchive(repo)
        if args.command == "init":
            result = archive.init_archive()
        elif args.command == "save":
            result = archive.save_url(args.url)
        elif args.command == "update-all":
            result = archive.update_all(force=args.force)
        elif args.command == "settings":
            if args.refresh_interval_days is None:
                result = archive.get_settings()
            else:
                result = archive.update_settings({"refresh_interval_days": args.refresh_interval_days})
        else:
            parser.error("unknown command")
            return 2
    except WikiSaverError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 1

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
