# herdr-codex-limits

A thin strip at the bottom of the [Herdr](https://herdr.dev) desktop app that shows
your Codex (ChatGPT plan) usage limits: the 5-hour and weekly windows, as a bar,
percent used and the time left until each one resets.

![codex-limits](preview.png)

```
<logo> ━━━━━ 11% 4h 27m · ━━━━━ 35% 2d 2h
```

- The bar and percent turn the theme's yellow from 80% and red from 95%.
- Time left reads `48m`, `4h 48m` or `2d 2h`.
- It refreshes every 5 minutes and about 15 s after a window resets. Click the strip
  to refresh now.
- If a refresh fails, the last values stay, dimmed, with `· stale 12m`; it retries
  after 1 minute, backing off to 5 minutes.
- Signed out or using an API key: the logo and `not signed in`. No `codex` found:
  `not installed`.

## Requirements

- The Herdr desktop app (built and tested on herdr-app 0.1.14, Linux)
- Codex CLI 0.48 or newer, signed in with a ChatGPT account (`codex login`)
- `python3` (standard library only)

## Install

```sh
git clone <this repo> && cd herdr-codex-limits
./install.sh            # copies mods/codex-limits into ~/.config/herdr-app/mods/
./install.sh --force    # replace an existing copy
```

`HERDR_APP_HOME` selects another app home.

**Watch out:** the app docks the strip into whichever layout is shown at install
time (the first time it sees the mod folder). Other layouts don't get it, so switch
to the layout you want before running `install.sh`.

### Finding `codex`

The helper looks for `codex` in this order:

1. `CODEX_BIN`, if set in the app's environment (an explicit path; nothing else is tried);
2. the app's `PATH`;
3. your login shell's `PATH` (`$SHELL -lc 'command -v codex'`), for apps started from a
   desktop launcher that didn't get your shell's `PATH`.

## Uninstall

```sh
rm -rf ~/.config/herdr-app/mods/codex-limits
```

The app then drops the strip. The last values are kept in the app's `shared.json` under
the `codex-limits` key; they're harmless, and the app owns that file.

## Privacy

The mod runs `codex app-server` locally and asks it for `account/rateLimits/read`. It
never reads `~/.codex/auth.json` and makes no network calls of its own; Codex answers
with its own login. No model request is made.

## Development

```sh
python3 -m unittest discover -s tests -v   # helper tests, against a fake codex
herdr-app check mods/codex-limits
```

## License

MIT
