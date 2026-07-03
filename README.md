# Wikipedia Saver

A local Wikipedia archiver with:

- a browser button on Wikipedia article pages
- a local Python server that saves pages into `~/Library/Application Support/WikipediaSaver/local-wiki`
- git history for every saved page
- a macOS updater that checks daily and refreshes when your configured interval has elapsed

## Install

From this directory:

```sh
chmod +x scripts/*.sh
./scripts/install-macos-launchagents.sh
```

Then load the unpacked browser extension:

1. Open `chrome://extensions` or `edge://extensions`.
2. Enable developer mode.
3. Choose "Load unpacked".
4. Select this folder: `extension`.

Wikipedia article pages will show a "Save to local wiki" button in the lower-right corner.

To set the refresh interval, open the extension details in `chrome://extensions` or `edge://extensions` and choose "Extension options".

The macOS installer stages the background runtime and default LaunchAgent archive under:

```text
~/Library/Application Support/WikipediaSaver/
```

This avoids macOS privacy restrictions that can prevent LaunchAgents from running code or writing data under Desktop/Documents folders. To force a different archive location during install:

```sh
WIKIPEDIA_SAVER_REPO="/path/to/local-wiki" ./scripts/install-macos-launchagents.sh
```

## Usage

Manual save from the command line:

```sh
python3 -m wiki_saver.cli init
python3 -m wiki_saver.cli save "https://en.wikipedia.org/wiki/Wikipedia"
```

Refresh every saved page:

```sh
python3 -m wiki_saver.cli update-all
python3 -m wiki_saver.cli update-all --force
python3 -m wiki_saver.cli settings --refresh-interval-days 14
```

Run the local browser-extension server manually:

```sh
python3 -m wiki_saver.cli serve
```

## Archive Layout

The default archive is `~/Library/Application Support/WikipediaSaver/local-wiki` for the CLI, local server, and installed macOS background service.

Saved pages are written like this:

```text
local-wiki/
  index.json
  pages/
    Wikipedia/
      article.wikitext
      article.html
      metadata.json
    fr.wikipedia.org/
      Paris/
        article.wikitext
```

English Wikipedia pages are stored directly under `pages/`. Other Wikipedia sites, including non-English sites, are grouped by hostname under `pages/<site>/`.

Useful git commands inside the archive:

```sh
cd "$HOME/Library/Application Support/WikipediaSaver/local-wiki"
git log --stat
git diff HEAD~1 -- pages/Wikipedia/article.wikitext
git checkout HEAD~1 -- pages/Wikipedia/article.wikitext
```

## macOS Services

The installer creates:

- `~/Library/LaunchAgents/com.local.wikipedia-saver.server.plist`
- `~/Library/LaunchAgents/com.local.wikipedia-saver.weekly.plist`

The server starts at login and stays running. The updater checks daily at 9:00 AM and refreshes only when the configured interval has elapsed.
