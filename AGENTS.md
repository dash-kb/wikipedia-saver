# Agent Notes

## Project Shape

- `wikipedia-saver/` is the tool implementation.
- `../local-wiki/` is the saved-page git archive created and updated by the tool.
- Keep saved Wikipedia content out of this project directory.
- The default archive path is intentionally `../local-wiki`; preserve that separation unless the user asks to change it.

## Architecture

- The browser extension injects the page button from `extension/content.js`.
- The extension performs localhost requests from `extension/background.js`.
- The local backend listens on `127.0.0.1:8765`.
- The backend code is in `wiki_saver/` and uses only the Python standard library plus the system `git` command.
- macOS automation is handled by LaunchAgents generated from `scripts/install-macos-launchagents.sh`.

## Common Commands

Run from `wikipedia-saver/`:

```sh
python3 -m unittest discover -s tests
python3 -m compileall -q wiki_saver tests
python3 -m json.tool extension/manifest.json >/dev/null
python3 -m wiki_saver.cli init
python3 -m wiki_saver.cli save "https://en.wikipedia.org/wiki/Wikipedia"
python3 -m wiki_saver.cli update-all
python3 -m wiki_saver.cli serve
```

Inspect the archive:

```sh
git -C ../local-wiki status --short
git -C ../local-wiki log --oneline --stat
```

## Maintenance Rules

- Keep the backend dependency-free unless a new dependency clearly removes meaningful complexity.
- Do not rewrite the archive history unless the user explicitly asks.
- Do not delete or revert saved pages in `../local-wiki` without explicit user direction.
- If changing the extension/backend request contract, update both `extension/background.js` and `wiki_saver/server.py`.
- If changing archive file layout, update `README.md`, tests, and any index-writing logic in `wiki_saver/saver.py`.
- Browser extension changes should remain Manifest V3 compatible.

## Sandbox Notes

- Sandboxed agents may not be able to write to `~/Library/LaunchAgents` or keep detached server processes alive.
- If LaunchAgent installation fails inside the sandbox, leave the script intact and tell the user to run:

```sh
cd /Users/dpkb/Desktop/projects/wikipedia-saver
./scripts/install-macos-launchagents.sh
```
