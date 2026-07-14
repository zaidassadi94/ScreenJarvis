# ScreenJarvis — project guide for Claude Code

> **⚠️ Session-start check:** `HANDOFF.md` may open with an "ACTION REQUIRED"
> block (e.g. rotate exposed API keys). If it does and the box is unchecked,
> surface it to the user first thing before other work.

Push-to-talk dictation that can *see your screen*. Hold a key, talk, and point
with the cursor; release and get a markdown document interleaving the spoken
words with auto-annotated screenshots of what was pointed at — an async screen
share for Claude Code, a blog, or a bug report. macOS for recording; the
compile pipeline runs anywhere.

## Architecture (the load-bearing split)

**Recorder** (platform-specific, dumb) captures continuously — never interprets
live. **Compiler** (platform-agnostic) extracts all meaning afterwards from the
saved bundle. Because the bundle preserves everything, the interpreter is
swappable without touching capture.

```
src/screenjarvis/
  recorder/     capture.py (CaptureSession lifecycle), audio, frames, events,
                hotkey, record (CLI flow). Lazy platform imports (sounddevice/
                mss/pynput) so the compiler stays importable headless.
  compiler/     stt (word-timestamped transcription; key routing by prefix),
                gestures (circle/wiggle/dwell from the 15Hz cursor log),
                keyframes (frame shortlist), understand (Claude pass →
                structured plan), annotate (rings/region highlights/cursor
                trails), render, compile (pipeline: transcript → understand →
                figures → transcript.md; smart mode with basic fallback),
                deliver (project transcript.md → text / self-contained HTML).
  app/          controller (platform-free brain, fully tested), menubar (rumps
                shell, macOS), notify (macOS verbs: paste, rich clipboard, key
                dialog), launchagent (start-at-login).
  packaging/    setup_app.py (py2app), app_entry, icon/make_icon.py, BUILD.md;
                scripts/build_app.sh builds ScreenJarvis.app + DMG (macOS).
  config.py     defaults ← ~/.config/screenjarvis/config.toml ← env. API keys
                may live in the config; apply_api_keys() makes them AUTHORITATIVE
                over stale shell env vars (env is only a fallback).
  setup_wizard.py   `sj setup` — line-preserving TOML merge.
  devtools/synth.py  synthetic session so the whole pipeline runs headless.
```

Session bundle: `sessions/<ts>/{transcript.md, images/, raw/{audio.wav,
events.jsonl, frames/, transcript.json, ...}}`.

## Two compile modes
- **smart** (default when an Anthropic key is set): Claude reads the timestamped
  transcript + gesture/click timeline + trail-overlaid frames → plans title,
  cleaned prose, figures, point/region highlights, captions.
- **basic**: offline heuristic (trigger phrases × cursor × clicks). Automatic
  fallback on any smart failure — a recording is never lost.

## Working here
- Run/test: `uv run pytest -q` (64 tests). Headless demo:
  `uv run sj synth && uv run sj compile synth-session && uv run sj export synth-session --format html`.
- Don't run the recorder here — mic/screen aren't available; use the synth path.
  The macOS shell (rumps/py2app/osascript) also can't run here — keep logic in
  the platform-free layer (controller, deliver) where it's testable.
- Match existing style: module docstrings stating design constraints, small
  focused modules, comments only for non-obvious constraints, modern typing.
- Develop on branch `claude/screenjarvis-macos-app-output-wnbu25`; commit + push
  per the repo's git conventions.

## Current state & next task
Working end-to-end on macOS. Output layer + installable app landed (see
`DECISIONS.md`): auto-paste default, rich clipboard, self-contained HTML,
`sj export`, and a py2app `.app`/`.dmg` with in-app key entry. **Open next:**
(1) still-untuned smart mode over-includes figures (9 for ~90s) — make the
understanding prompt selective / add a max-figures cap; (2) a signed+notarized
public build (Developer ID + CI on tag); (3) deferred outputs — portable
Markdown, PDF, image hosting. See `DECISIONS.md`, `HANDOFF.md`, `PLAN.md`.
