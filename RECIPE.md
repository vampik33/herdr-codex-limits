# Codex limits

A thin full-width strip at the bottom of the window that shows the person's Codex
(ChatGPT plan) usage limits in one monospace line: the 5-hour and weekly windows, each
as a bar, percent used and the time left until it resets.

![Codex limits](preview.png)

## What you see

One block docked at the bottom of the layout, 26px tall, full window width, `chrome`
background with a 1px `border` line on top. One line of text in the layout's terminal
font (`settings().font_family`, else JetBrains Mono) at the UI text size
(`settings().ui_font_size`, 13px by default), 14px padding left and right, vertically
centered:

```
<logo> ━━━━━ 11% 4h 27m · ━━━━━ 35% 2d 2h
```

- `<logo>` is the OpenAI symbol (`codex.svg`, drawn with `svg(...)` at the text size) in
  `muted`. The 5-hour window comes first, then the weekly one, with no labels; a `dim`
  `·` separates them. The time left is `dim`.
- The bar is 5 monospace cells wide and 5px tall, fully rounded: a `border`-colored
  track with a fill `percent`% of its width. Fill and percent share one color:
  `foreground` below 80%, `ansi3` (yellow) from 80%, `ansi1` (red) from 95%.
- Spacing is 1 monospace cell (0.6 × text size, rounded) between every item.
- Time left until the reset: `48m` under an hour, `4h 48m` under a day, else `2d 2h`.
- No data yet: `<logo> …`. Never fetched successfully and Codex is signed out or uses
  an API key: `<logo> not signed in`; no `codex` program: `<logo> not installed`; other
  failure: `<logo> unavailable`.
- Stale (the last fetch failed but older values exist): the whole line at 50% opacity,
  followed by `· stale <age>` in `dim` (`12m`, `3h`, `2d`).

## How it behaves

- No agent statuses: it shows account data, not agents.
- Fetches on start, then every 5 minutes, and 15 s after any shown window's reset time.
- Click anywhere on the strip: fetch now. Only one fetch runs at a time; a click during
  one does nothing.
- A failed fetch keeps the last good values (stale) and retries after 1 minute,
  doubling up to 5 minutes; a success resets the backoff.
- A window whose reset time has passed disappears until the next fetch brings it back.
- The line redraws once a minute (stale age, expiry, time left) and after each
  fetch; nothing animates.
- The last good values persist across reloads and restarts in shared state.

## Built from

- No layout: one mod, `mods/codex-limits/`, with `mod.json`
  `{ "place": "bottom", "size": 26 }` so the app docks it under the shown layout the
  first time it sees the folder. No props.
- `main.js`: a `View` with `init` (reads `shared("codex-limits")`, starts
  `cx.timer.every(5000)` and a first fetch) and `render`. Uses `exec`, `appHome`,
  `theme`, `settings`, `shared`, `setShared` from `herdr`, `div` and `svg` from `gpui-kit`,
  `h_flex` from `gpui-base`. The fetch is
  `exec("python3", [appHome() + "/mods/codex-limits/codex_limits.py"], { timeout: 25000 })`
  inside `cx.spawn`. Shared key `codex-limits` holds `{ windows, fetchedAt }` (ms).
- `codex_limits.py` (Python 3 standard library): runs `codex app-server` and speaks
  newline-delimited JSON-RPC on stdio: `initialize` (id 0, clientInfo
  `herdr-codex-limits`), `initialized`, then `account/rateLimits/read` (id 1); lines
  without the awaited id are skipped. From `result.rateLimits.primary`/`secondary` it
  keys each window by `windowDurationMins` (300 → `5h`, 10080 → `wk`), never by slot.
  It prints exactly one line: `{"windows":{"5h":{"usedPercent","resetsAt"},...},
  "plan","fetchedAt"}` or `{"error":"not_signed_in"|"codex_missing"|"timeout"|"failed",
  "detail"}`. `resetsAt` is Unix seconds.
- Finds `codex` via `CODEX_BIN`, then `PATH`, then `$SHELL -lc 'command -v codex'`.
- Art: `codex.svg`, the OpenAI symbol as one path, drawn with `svg(...)` so it takes
  the text color. No keys.

## Watch out

- `exec` cannot write to a program's stdin, hence the helper script.
- The helper must always kill `codex app-server`: an npm/pnpm `codex` is a shim that
  starts node, which starts the real binary. Start it in its own process group
  (`start_new_session`) and kill the group (TERM, up to 1 s for the shim, then KILL the whole group even if the
  shim already exited, since a child may ignore TERM), on success, error and the
  15 s overall timeout (`CODEX_LIMITS_TIMEOUT` overrides it, for tests).
- Send nothing to stderr and nothing but the one line to stdout; the child's stderr goes
  to `/dev/null`.
- Signed-out and API-key accounts return an error or no windows; map both to
  `not_signed_in` (an error message mentioning auth/login, or no usable window).
- `herdr-app check` writes `gpui-kit.d.ts` and `jsconfig.json` into the mod folder; they
  are the app's, not the mod's.
- The app docks the strip into whichever layout is shown at install time (when it first
  sees the folder);
  other layouts don't get the strip.
- A copy keeps polling while hidden; the 5 s tick only compares times and redraws once a
  minute.
- Only `5h` and `wk` windows are shown; other durations are ignored.

## Done when

- `python3 -m unittest discover -s tests` passes: normal response, windows swapped
  between primary and secondary, null secondary, auth error, other error, notifications
  and junk before the result, child exit, a hanging child timing out with its whole tree
  killed (also when a grandchild ignores SIGTERM), `codex` missing, `CODEX_BIN` override and login-shell lookup.
- Running the helper by hand prints one JSON line with `5h` and `wk` windows and leaves
  no `codex app-server` behind.
- `herdr-app check mods/codex-limits` passes and `herdr-app status` shows no errors.
- The strip shows at the bottom of the window with both windows, each with a bar and
  the time left.
- With `codex` made unreachable, the strip dims and shows `· stale 1m` after a reload;
  with no saved values, it shows `<logo> …` while fetching, then `<logo> not installed`.
