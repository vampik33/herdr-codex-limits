import { View, div, svg } from "gpui-kit";
import { h_flex } from "gpui-base";
import { exec, appHome, theme, settings, shared, setShared } from "herdr";

// Codex (ChatGPT plan) usage limits: the 5-hour and weekly windows.
// codex_limits.py asks the local `codex app-server` and prints one JSON line.
const STATE = "codex-limits"; // shared key: the last good { windows, fetchedAt }
const POLL_MS = 5 * 60_000;
const RETRY_MS = 60_000;
const AFTER_RESET_MS = 15_000;
const METER_W = 48; // bar size in px, the same as the claude-limits strip
const METER_H = 6;
const MESSAGES = { not_signed_in: "not signed in", codex_missing: "not installed" };

// Time left until a reset: "48m", "4h 48m", "2d 2h".
function countdown(ms) {
  const m = Math.max(0, Math.floor(ms / 60_000));
  if (m < 60) return `${m}m`;
  if (m < 1440) return `${Math.floor(m / 60)}h ${m % 60}m`;
  return `${Math.floor(m / 1440)}d ${Math.floor((m % 1440) / 60)}h`;
}

function age(ms) {
  const m = Math.max(1, Math.floor(ms / 60_000));
  return m < 60 ? `${m}m` : m < 1440 ? `${Math.floor(m / 60)}h` : `${Math.floor(m / 1440)}d`;
}

export default class CodexLimits extends View {
  init(_props, cx) {
    this.last = shared(STATE) ?? null; // survives reloads
    this.error = null; // the latest fetch's error code, null after a success
    this.busy = false;
    this.failures = 0;
    this.nextAt = 0;
    this.minute = 0;
    cx.timer.every(5_000, (cx) => this.tick(cx));
    this.refresh(cx);
  }

  tick(cx) {
    const now = Date.now();
    if (now >= this.nextAt) this.refresh(cx);
    // Redraw once a minute: stale age, expired windows, "today" vs weekday.
    const minute = Math.floor(now / 60_000);
    if (minute !== this.minute) {
      this.minute = minute;
      cx.notify();
    }
  }

  refresh(cx) {
    if (this.busy) return;
    this.busy = true;
    cx.spawn(async (cx) => {
      let out;
      try {
        const r = await exec("python3", [`${appHome()}/mods/codex-limits/codex_limits.py`], { timeout: 25_000 });
        out = JSON.parse(r.stdout.trim().split("\n").pop() || "{}");
      } catch (_e) {
        out = { error: "failed" };
      }
      const now = Date.now();
      if (out && out.windows && !out.error) {
        this.last = { windows: out.windows, fetchedAt: now };
        setShared(STATE, this.last);
        this.error = null;
        this.failures = 0;
        const resets = Object.values(out.windows).map((w) => w.resetsAt * 1000 + AFTER_RESET_MS).filter((t) => t > now);
        this.nextAt = Math.min(now + POLL_MS, ...resets);
      } else {
        this.error = out?.error ?? "failed";
        this.failures += 1;
        this.nextAt = now + Math.min(RETRY_MS * 2 ** (this.failures - 1), POLL_MS);
      }
      this.busy = false;
      cx.notify();
    });
  }

  meter(w, t, now) {
    const pct = Math.max(0, Math.min(100, w.usedPercent));
    const level = pct >= 95 ? t.ansi1 : pct >= 80 ? t.ansi3 : null;
    return h_flex().items_center().gap(6)
      .child(div().w(METER_W).h(METER_H).flex_none().rounded_full().overflow_hidden().bg(t.border)
        .child(div().w((METER_W * pct) / 100).h_full().rounded_full().bg(level ?? t.muted)))
      .child(div().text_color(level ?? t.foreground).child(`${Math.round(pct)}%`))
      .child(div().text_color(t.foreground).child(countdown(w.resetsAt * 1000 - now)));
  }

  render() {
    const t = theme();
    const s = settings();
    const size = s.ui_font_size ?? 13;
    const now = Date.now();
    const windows = Object.entries(this.last?.windows ?? {})
      .filter(([, w]) => w.resetsAt * 1000 > now)
      .sort(([a], [b]) => (a === "5h" ? -1 : b === "5h" ? 1 : 0));
    const stale = Boolean(this.error && this.last);

    const row = h_flex().id("codex-limits").size_full().px(14).items_center().gap(8)
      .bg(t.chrome).border_t(1).border_color(t.border).cursor_pointer()
      .text_size(size).text_color(t.muted).whitespace_nowrap()
      .on_click((_e, cx) => this.refresh(cx));

    // 0.85 × text size: as wide as the claude-limits ✻, so both strips' bars start at the same x.
    const logo = svg("mods/codex-limits/codex.svg").size(Math.round(size * 0.85)).flex_none().text_color(t.muted);
    if (!this.last && this.error) {
      return row.child(h_flex().items_center().gap(8).child(logo).child(MESSAGES[this.error] ?? "unavailable"));
    }

    const body = h_flex().items_center().gap(8).when(stale, (el) => el.opacity(0.5))
      .child(logo)
      .when(windows.length === 0, (el) => el.child("…"))
      .children(windows.flatMap(([, w], i) =>
        [...(i ? [div().text_color(t.dim).child("·")] : []), this.meter(w, t, now)]));
    return row.child(body)
      .when(stale, (el) => el.child(div().text_color(t.dim).child(`· stale ${age(now - this.last.fetchedAt)}`)));
  }
}
