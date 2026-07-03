# ScreenJarvis

Push-to-talk dictation that can see your screen. Hold a key, talk, and point with your cursor — say "look at this" and it captures what you meant. Release the key and get a markdown document with your words interleaved with auto-annotated screenshots: an async screen share you can paste into Claude Code, a blog post, or a bug report.

**Status:** Phase 0 spike (see [PLAN.md](PLAN.md)). Recording targets macOS; the compile pipeline runs anywhere.

## Install

```sh
git clone https://github.com/zaidassadi94/ScreenJarvis && cd ScreenJarvis
uv sync
uv run sj --help
```

## Record

```sh
export OPENAI_API_KEY=sk-...   # or GROQ_API_KEY (faster + cheaper)

uv run sj record               # starts immediately; press Enter to stop
uv run sj record --hold        # hold right-Option (alt_r) to record, release to stop
```

Talk about what's on screen and point with your cursor; click things to pin them precisely. Phrases like *"look at this"*, *"this error right here"*, *"see this button"* each become an annotated screenshot with a ring drawn where your cursor was.

The result is a self-contained bundle:

```
~/ScreenJarvis/sessions/2026-07-03_14-22-05/
  transcript.md      # your words + inline figures (relative paths)
  images/            # fig-01.jpg, fig-02.jpg ...
  raw/               # audio, all frames, event log, word-level transcript
```

## Hand it to Claude Code

```sh
claude "Read $(uv run sj last)/transcript.md and help me fix what I describe"
```

Claude reads the markdown and the figures natively — no hosting, no uploads.

## Recompile

```sh
uv run sj compile last                 # re-run the pipeline (reuses the transcript)
uv run sj compile last --stt openai    # force re-transcription
```

## macOS permissions

First run will prompt for **Microphone**, **Screen Recording**, and **Accessibility / Input Monitoring** (global hotkey + cursor tracking). Grant them to your terminal app under System Settings → Privacy & Security, then re-run.

## Config (optional)

`~/.config/screenjarvis/config.toml`:

```toml
sessions_dir = "~/ScreenJarvis/sessions"
stt = "auto"            # auto | openai | groq
hold_key = "alt_r"
crop = "none"           # none | region (crop figures around the cursor)
extra_trigger_phrases = ["this widget", "this dashboard"]
```

## Develop (no mic or screen needed)

The recorder and compiler are split by a file contract, so the whole pipeline runs headless against a synthetic session:

```sh
uv run sj synth && uv run sj compile synth-session
uv run pytest
```

## Roadmap

Phase 0 (this spike) → menu-bar app → Claude cleanup + vision captions → hosting/MCP. Details in [PLAN.md](PLAN.md).
