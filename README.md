# Wikipedia Saver

A local Wikipedia archiver with:

- a browser button on Wikipedia article pages
- a local Python server that saves pages into `../local-wiki`
- git history for every saved page
- a weekly macOS updater that refreshes saved pages and commits changes

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

## Usage

Manual save from the command line:

```sh
python3 -m wiki_saver.cli init
python3 -m wiki_saver.cli save "https://en.wikipedia.org/wiki/Wikipedia"
```

Refresh every saved page:

```sh
python3 -m wiki_saver.cli update-all
```

Run the local browser-extension server manually:

```sh
python3 -m wiki_saver.cli serve
```

## Archive Layout

Saved pages are written to `../local-wiki`:

```text
local-wiki/
  index.json
  pages/
    en.wikipedia.org/
      Wikipedia/
        article.wikitext
        article.html
        metadata.json
```

Useful git commands inside `../local-wiki`:

```sh
git log --stat
git diff HEAD~1 -- pages/en.wikipedia.org/Wikipedia/article.wikitext
git checkout HEAD~1 -- pages/en.wikipedia.org/Wikipedia/article.wikitext
```

## macOS Services

The installer creates:

- `~/Library/LaunchAgents/com.local.wikipedia-saver.server.plist`
- `~/Library/LaunchAgents/com.local.wikipedia-saver.weekly.plist`

The server starts at login and stays running. The weekly updater runs Monday at 9:00 AM.
