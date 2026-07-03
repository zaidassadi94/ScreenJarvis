# ScreenJarvis — Plan

**One-liner:** Wispr-style push-to-talk dictation that can *see your screen* — so "look at this" actually means something. Hold a key, talk, point with your cursor; release the key and get a clean markdown document where your words are interleaved with auto-annotated screenshots of exactly what you were pointing at. An async screen share you can paste into Claude Code, a blog post, or a bug report.

---

## 1. The problem

Voice is the fastest way to explain something to an AI (or a person), but explanations about *visual* things constantly reference the screen: "this button", "look at this error", "this part of the chart". Today the workflow is: talk/type, stop, take a screenshot, maybe open it in an editor to draw a circle, paste it, describe where to look, repeat. The deixis — the pointing — is lost, and reconstructing it manually is the whole cost.

A live screen share solves this between humans because the other person sees your cursor while you talk. ScreenJarvis reproduces that for asynchronous consumers: AI agents, blog readers, teammates.

**What it is not:** not a live screen share, not a video recorder (Loom), not always-on ambient screen memory (Rewind/Recall). It records only while you hold the key — same trust model as Wispr Flow — and its output is *stills + text*, because that's what markdown, blogs, and AI context windows want.

## 2. The core interaction

1. **Hold the hotkey** (or tap to toggle). A small indicator shows recording is live.
2. **Talk and point.** Move your cursor to things as you reference them; click on them if you like. Say things like "look at this", "this error here", "see how this overflows".
3. **Release.** Processing runs for a few seconds (transcribe → find pointing moments → grab & annotate frames → render).
4. **Get the bundle.** A notification offers: open folder / copy markdown / copy path. The bundle is a folder:

```
sessions/2026-07-03_14-22-05/
  transcript.md      # the deliverable: prose + inline figures (relative paths)
  images/            # annotated figures: fig-01.png, fig-02.png ...
  raw/
    audio.wav
    frames/          # all captured frames (kept until you delete the session)
    events.jsonl     # cursor track, clicks, active-window changes
    transcript.json  # word-level STT output
```

Example `transcript.md`:

```markdown
## Session — 2026-07-03 14:22 (1m 43s)

We need to fix the layout bug on the pricing page. Look at this — the middle
card overflows its container when the billing toggle is set to annual.

![Fig 1 — pricing page, middle card overflowing](images/fig-01.png)

The problem is this flex rule here; `min-width` is fighting the gap.

![Fig 2 — devtools, .price-card rule highlighted](images/fig-02.png)
```

Because paths are relative and images are ordinary PNGs, **the Claude Code integration is free**: point Claude at `transcript.md` and it reads the text and the images natively. No hosting required for the primary use case.

### Vocabulary

- **Session** — one press-to-release recording.
- **Anchor** — a moment where speech references the screen (detected from words + cursor + clicks).
- **Figure** — the rendered, annotated image produced for an anchor.

## 3. Architecture

Two halves with a file-based contract between them, so each can be swapped independently:

```
┌──────────────── Recorder (platform-specific, dumb & reliable) ────────────────┐
│ global hotkey │ mic → audio.wav │ frames @ ~2fps → raw/frames/ │ events.jsonl │
│               │  (16kHz mono)   │ + extra frame on every click │ cursor @15Hz │
│               │                 │ (display containing cursor)  │ clicks, app  │
└───────────────────────────────┬──────────────────────────────────────────────┘
                                ▼   everything timestamped against one t0
┌──────────────── Compiler (platform-agnostic pipeline) ────────────────────────┐
│ 1. STT with word-level timestamps                                             │
│ 2. Anchor detection: trigger phrases × cursor activity × clicks               │
│ 3. Frame selection + annotation (ring at cursor, optional crop to window)     │
│ 4. (Phase 2) LLM pass: clean prose, figure captions, structure               │
│ 5. Render transcript.md + images/                                             │
└───────────────────────────────────────────────────────────────────────────────┘
```

`events.jsonl` sample:

```jsonl
{"t": 12.41, "type": "cursor", "x": 1490, "y": 622, "display": 1}
{"t": 13.02, "type": "click", "x": 1492, "y": 620, "button": "left"}
{"t": 13.02, "type": "window", "app": "Google Chrome", "title": "Pricing – Acme"}
```

### Why frames + cursor log instead of recording a video

- The output is stills, so capturing stills avoids a decode/extract step and an enormous intermediate file.
- A cursor log at 15 Hz is ~free and gives *exact* pointer coordinates at any word's timestamp — more precise than reading the cursor out of video pixels.
- ~2 fps JPEG (downscaled to ≤1600px wide, quality ~80) ≈ 100–300 KB/frame → a 3-minute session is ~50–100 MB of raw frames, deleted or pruned after compile. Sessions are voice-memo-length (30s–5min), not recordings.
- Short video clips around an anchor ("watch this animation") can be added later precisely *because* the recorder abstraction doesn't care.

### Anchor detection (MVP algorithm)

1. Transcribe with word timestamps.
2. Scan for trigger phrases — multi-word to avoid false fires on bare "this": *look at this / this here / right here / see this / this one / this error / over here / this part*, etc. (configurable list).
3. For each hit at time *t*: interpolate cursor position at *t* from `events.jsonl`; pick the frame nearest *t* within ±0.7s — preferring a frame just after a click if one occurred within ~1s (clicks are the strongest pointing signal).
4. Merge anchors < 2s apart (same gesture, restated).
5. Render the figure: draw a high-contrast ring/halo at the cursor coordinates; optionally crop to the active window or a region around the cursor with padding (keeps figures focused and small). Full frame always kept in `raw/`.
6. Insert the figure after the sentence containing the trigger.

Design bias: **over-capture, then curate.** An extra figure is a two-second delete; a missed one kills trust in the tool. Phase 2 adds better signals (cursor dwell/wiggle detection — people naturally circle the cursor while saying "this"; an LLM pass that reads the transcript and decides what's referenced).

## 4. Key technical decisions

### Speech-to-text — needs word-level timestamps (hard requirement)

Alignment of "look at **this**" to a cursor position lives or dies on word timing. (Note: Wispr Flow itself has no public API — what we actually want is the Whisper family or a streaming STT vendor.)

| Option | Word timestamps | Notes |
|---|---|---|
| OpenAI `whisper-1` | ✅ (`verbose_json` + word granularity) | Simple, accurate, ~$0.006/min (a 2-min session ≈ 1¢) |
| Groq `whisper-large-v3-turbo` | ✅ | Very fast + cheap; good default |
| Deepgram (nova) | ✅, streaming | Needed later if we want *real-time* triggers |
| Local: `faster-whisper` / `mlx-whisper` / whisper.cpp | ✅ | Free, private, offline; a settings toggle |

**Recommendation:** cloud Whisper (OpenAI or Groq) for the spike — zero tuning, pennies — with a local backend added early as the privacy option. Streaming STT is *not* needed in v1 because anchors are resolved after the fact from the frame buffer; nothing has to trigger in real time.

### LLM pass (Phase 2) — Claude

- **Cleanup:** raw speech → readable prose (remove fillers, false starts; keep meaning and the trigger sentences intact) — the Wispr-style polish.
- **Captions:** send the annotated frame + cursor coords to Claude vision → "Fig 2 — devtools, `.price-card` rule highlighted" instead of "Fig 2". Also alt text.
- **Judgment:** a transcript-level pass that catches references the lexical list missed ("the thing in the corner is wrong") and proposes anchors for them.
- Model: `claude-opus-4-8` while iterating on prompts; downshift cleanup to Haiku 4.5 once stable. Cloud vision on frames is **opt-in** (screen contents are sensitive) — cleanup-only mode sends text only.

### Output modes (later)

Same session, different renders: **for-AI** (verbose, precise, file paths, full frames available), **for-blog** (polished prose, curated figures, hosted images), **bug report** (repro-steps template). MVP ships one generic markdown; modes are just prompt + template variants over the same bundle.

### Hosting (Phase 3, blog case only)

Local bundle covers Claude Code and most sharing. For blogs: "copy portable markdown" uploads `images/` to object storage (Cloudflare R2 / S3 presigned; or a GitHub gist for dev users) and rewrites URLs. Explicitly opt-in per session.

### Platform & stack

The pipeline is platform-agnostic; only the recorder is platform-specific. **Assumption: macOS first** (flag if wrong — see Open Questions).

- **Phase 0–1: Python.** `sounddevice` (mic) + `mss` (screenshots, multi-monitor) + `pynput` (global hotkey, cursor, clicks) + `Pillow` (annotation) + `rumps` (menu-bar shell). Run via `uv` from a terminal; grant mic/screen-recording/accessibility permissions to the terminal app during development. This is days-to-working, which is what validation needs.
- **Phase 3+ (only if distributing to others):** rewrite the shell in Tauri or Swift/ScreenCaptureKit for signing, packaging, and polish. The pipeline and bundle format carry over untouched. Deciding this now would be premature — the pipeline is the asset, the shell is cheap.

### Privacy posture (a feature, not a footnote)

- Records **only while the key is held** — nothing ambient, ever.
- Local-first: frames never leave the machine unless vision captions or hosting are explicitly enabled; STT sends audio only (or nothing, with a local backend).
- Later: redaction pass (blur emails/tokens/notification popups) before any upload.

## 5. Roadmap

### Phase 0 — pipeline spike (a weekend)
CLI, no UI polish: run command → hold key → talk & point → release → `transcript.md` opens.
**Proves/kills the core bet:** does word-time × cursor-position produce figures that match intent?
**Acceptance:** narrate a real code review for 60–90s pointing at 3 things → ≥2 of 3 figures are correctly placed and correctly annotated, with zero manual fixing.

### Phase 1 — daily-drivable (1–2 weeks)
Menu-bar app (still Python/rumps): hold-to-talk from anywhere, auto-compile on release, notification → open/copy actions, `sessions/` management, config file (STT backend, trigger phrases, crop mode, hotkey). A tiny `sj last` CLI that prints/copies the latest bundle path (the Claude Code hand-off).
**Acceptance:** self-use for every Claude Code session and one written explanation per day for a week, without touching a terminal.

### Phase 2 — smarts
Claude cleanup + captions + missed-anchor detection; cursor-dwell/wiggle as an anchor signal; auto-crop to active window with zoom inset; output modes (for-AI / for-blog); redaction blur.
**Acceptance:** a session drops into a blog draft with < 1 minute of editing.

### Phase 3 — sharing & integrations
Image hosting + portable markdown; HTML export; MCP server exposing `latest_session` / `get_session(n)` to Claude Code; optional short video clips around anchors; app-shell rewrite (Tauri/Swift) if distributing.

## 6. Risks

| Risk | Mitigation |
|---|---|
| Anchor precision: cursor at word-time ≠ what was meant | Clicks preferred over hover; ±0.7s window; over-capture + keep all raw frames for manual fix-up; Phase-2 LLM judgment pass |
| Trigger recall/precision (bare "this" is everywhere) | Multi-word phrase list + require cursor activity near *t*; tune on own real sessions before adding cleverness |
| Python packaging/permissions pain | Personal tool first (terminal-granted permissions); packaging deferred to Phase 3 |
| Screen frames are sensitive | Local-first defaults; cloud vision & hosting strictly opt-in; redaction before upload |
| Scope creep toward a Loom clone | Stills + markdown is the wedge; video is a Phase-3 maybe, never the center |

## 7. Open questions (assumptions in effect until answered)

1. **OS** — assumed **macOS** first. (Windows recorder is a straightforward second target given the recorder/compiler split.)
2. **Cloud STT acceptable?** — assumed **yes** (audio to OpenAI/Groq); local Whisper as the privacy toggle.
3. **First consumer** — assumed **Claude Code** (zero-hosting path), with blog polish arriving in Phase 2–3. If blogging is actually the primary target, hosting and the cleanup pass move earlier.
4. **v0 as a Python CLI acceptable?** — assumed yes; a native-feeling app is Phase 3.
