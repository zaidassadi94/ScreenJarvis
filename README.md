# ScreenJarvis

Push-to-talk dictation that can see your screen. Hold a key, talk, and point with your cursor — say "look at this" and it captures what you meant. Release the key and get a markdown document with your words interleaved with auto-annotated screenshots: an async screen share you can paste into Claude Code, a blog post, or a bug report.

**Status:** Phase 1 — a resident macOS menu-bar app you can use every day (see [PLAN.md](PLAN.md)).

## Two ways to run it

- **As a Mac app** — build a double-clickable `ScreenJarvis.app` (menu-bar only,
  API keys entered in-app, no Terminal after install): see
  [packaging/BUILD.md](packaging/BUILD.md). A signed, notarized download is
  planned; until then you build it yourself with `./scripts/build_app.sh`.
- **From the terminal with `uv`** — the fastest way to try it, below. Same app,
  launched with `uv run sj app`.

## Set up (10 minutes, one time)

You need a Mac and the Terminal app (it's in Applications → Utilities). Copy each block below into Terminal and press Enter.

**1. Install uv** (the tool that runs ScreenJarvis):

```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Close Terminal and open it again after this step, so the `uv` command is found.

**2. Download ScreenJarvis and install its dependencies:**

```sh
git clone https://github.com/zaidassadi94/ScreenJarvis
cd ScreenJarvis
uv sync
```

**3. Run the setup wizard:**

```sh
uv run sj setup
```

It asks for API keys and saves everything to a config file so you never type them again. You need:

- **One speech-to-text key** — either OpenAI ([platform.openai.com](https://platform.openai.com), API keys page) or Groq ([console.groq.com](https://console.groq.com), faster and cheaper). Transcription costs about a cent per session.
- **An Anthropic key** ([console.anthropic.com](https://console.anthropic.com)) — optional but recommended; it turns on smart mode (see below).

**4. Start the app:**

```sh
uv run sj app
```

A 🎙 icon appears in your menu bar at the top of the screen. Now do one test recording — hold the right Option key, say "testing, look at this" while pointing at something, and release. The first recording triggers macOS permission prompts; read the next section.

## macOS permissions (first recording only)

macOS protects the mic, screen, and keyboard, so the first recording will pop up permission prompts. All four live in **System Settings → Privacy & Security**:

| Pane | Why ScreenJarvis needs it |
|---|---|
| **Microphone** | record your voice |
| **Screen Recording** | capture screenshots |
| **Accessibility** | track the cursor you point with |
| **Input Monitoring** | see the hold-to-talk key anywhere, in any app |

Two things that trip people up:

- Grants attach to **the app that launched ScreenJarvis** — that's **Terminal** when you run `uv run sj app` yourself, or **"Python"** when it starts via the login item. If you switch between the two, you may need to grant the same panes to the other one.
- After granting **Screen Recording**, macOS often requires a re-launch before it takes effect: quit ScreenJarvis from its menu (or quit Terminal) and start it again.

If the hotkey does nothing or you see "could not start capture", it's almost always one of these panes — see Troubleshooting below.

## Every day after that

1. **Hold the right Option key** — anywhere, in any app. The menu-bar icon turns 🔴.
2. **Talk, point, click.** Move your cursor to the things you mention, click them to pin them precisely, circle things to highlight a whole area.
3. **Release.** The icon shows ⏳ while it compiles in the background — you can keep working, or even start the next recording.
4. **Your cleaned-up words paste themselves in** — wherever your cursor is (Wispr-style). The screenshots go into the session document for when you need them; see [Getting the output out](#getting-the-output-out).

Clicking the 🎙 icon opens the menu:

- **Status** — Ready / Recording… / Compiling…
- **Open Last Session** — opens the most recent transcript.md
- **Copy Text** — the cleaned narration, to paste anywhere
- **Copy Rich Text (with images)** — text + the screenshots, for Notion / Docs / email
- **Open as Web Page** — a self-contained HTML document of the session
- **Copy Claude Prompt** — a prompt pointing at the session, to paste into Claude Code
- **Open Sessions Folder** — all your recordings live here
- **Set API Keys…** — enter / change keys without opening Terminal
- **Open Config File** — edit settings (creates the file with all options listed)
- **Start at Login** — toggle so ScreenJarvis is always running
- **Quit ScreenJarvis**

To start at login from Terminal instead:

```sh
uv run sj app --install-login     # or --uninstall-login
```

Each recording becomes a self-contained folder:

```
~/ScreenJarvis/sessions/2026-07-03_14-22-05/
  transcript.md      # your words + inline figures (relative paths)
  images/            # fig-01.jpg, fig-02.jpg ...
  raw/               # audio, all frames, event log, word-level transcript
```

## Getting the output out

A recording compiles into one canonical document (`transcript.md` + `images/`).
From there ScreenJarvis gives it to you in the shape you need — pick the default
in the config (`on_done`), or reach for any of them on demand from the menu:

| You want to… | Use | What you get |
|---|---|---|
| Dictate into a text box | **paste-text** (default) | the cleaned narration typed straight into the focused app, like Wispr |
| Drop it into Notion / Docs / email | **Copy Rich Text** | formatted text **with the screenshots inline** (macOS rich clipboard) |
| Send a readable write-up / bug report | **Open as Web Page** | a single self-contained `.html` (images embedded); ⌘P → Save as PDF for a PDF |
| Hand it to Claude Code | **Copy Claude Prompt** | a prompt pointing at `transcript.md`, which Claude reads with its figures |

Images are **embedded** so every export is self-contained — nothing is uploaded,
it works offline. Hosting figures behind URLs is a planned option; the seam for
it is in place (see [DECISIONS.md](DECISIONS.md)). From Terminal:

```sh
uv run sj export last --format html --open   # write + open the web page
uv run sj export last --format text          # print the cleaned narration
```

## Smart vs basic mode

With an Anthropic key set, compiling uses **smart mode**: Claude reads the whole session — timestamped transcript, click/gesture timeline, screenshots with your cursor's path drawn on them — and plans the document: cleaned-up prose, which moments deserve figures (including references like "the thing in the corner" that match no trigger phrase), point vs. region highlights (circle something and the figure gets a ring around that area), and captions that name what's shown.

Without the key, **basic mode** runs: a fully offline heuristic that looks for trigger phrases like "look at this" and rings the cursor position. A failed smart compile always falls back to basic — a recording is never lost.

Privacy note: smart mode sends the selected screenshots (about a dozen per session) and transcript to the Anthropic API. Remove the key or pass `--basic` for a fully local compile (cloud speech-to-text is a separate choice).

## Config file

`~/.config/screenjarvis/config.toml` (or menu → Open Config File). Every key is optional; these are the defaults:

```toml
sessions_dir = "~/ScreenJarvis/sessions"
hold_key = "alt_r"               # right Option; also e.g. cmd_r, f8, or a single character
max_secs = 600.0                 # auto-stop watchdog
sounds = true                    # start/stop/done/error sounds
on_done = "paste-text"           # what releasing the key does with the result:
                                 # paste-text | copy-text | copy-rich | open-html | claude-prompt | path | off

stt = "auto"                     # auto | openai | groq
smart = "auto"                   # auto (Claude when key is set) | on | off
llm_model = "claude-opus-4-8"

# API keys may live here because the menu-bar app is launched outside any
# shell and inherits no environment variables (sj setup fills these in):
openai_api_key = ""
groq_api_key = ""
anthropic_api_key = ""

crop = "none"                    # none | region (crop figures around the cursor)
extra_trigger_phrases = ["this widget", "this dashboard"]
```

A key you save with `sj setup` is authoritative: it's used even if an old `OPENAI_API_KEY` / `GROQ_API_KEY` / `ANTHROPIC_API_KEY` is still set in your shell (so a leftover `export` can't silently break transcription). Environment variables still work as a fallback for any service you *haven't* configured with `sj setup`.

## CLI reference

You rarely need these once the app is running, but everything works from Terminal too:

| Command | What it does |
|---|---|
| `uv run sj setup` | interactive setup: API keys, hotkey, preferences |
| `uv run sj app` | run the menu-bar app |
| `uv run sj app --install-login` / `--uninstall-login` | start (or stop starting) at login |
| `uv run sj record` | record from the terminal; Enter stops |
| `uv run sj record --hold` | hold-to-record on the hotkey, release to stop |
| `uv run sj compile last` | (re)compile the latest session |
| `uv run sj compile last --basic` / `--smart` | force a compile mode |
| `uv run sj compile last --stt openai` | force re-transcription |
| `uv run sj export last --format html` | write a self-contained web page (`--open` to open it) |
| `uv run sj export last --format text` | print the cleaned narration |
| `uv run sj last` | print the latest session directory (`--open` to reveal) |
| `uv run sj synth` | generate a synthetic session (dev; no mic or screen) |

Hand a session to Claude Code manually:

```sh
claude "Read $(uv run sj last)/transcript.md and help me fix what I describe"
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| Holding the hotkey does nothing | Grant **Input Monitoring** to the launching app (Terminal, or "Python" for the login item), then restart ScreenJarvis |
| "Could not start recording / could not start capture" | Grant **Microphone** and **Screen Recording**; after granting Screen Recording, quit and re-launch |
| Screenshots are black or missing | Same as above — Screen Recording grants only apply after a re-launch |
| Transcript is fine but has no figures | In basic mode, no trigger phrase matched — say things like "look at this", "this error here", or click while talking. Or set an Anthropic key: smart mode catches references no phrase list would |
| Notification says "smart compile failed …" but a document was still produced | The Anthropic key is wrong/missing or the network hiccupped; the session was compiled in basic mode. Fix the key and re-run `uv run sj compile last --smart` |
| "Speech-to-text is not configured yet" notification | Run `uv run sj setup` and enter an OpenAI or Groq key |

## Develop (no mic or screen needed)

The recorder and compiler are split by a file contract, so the whole pipeline runs headless against a synthetic session:

```sh
uv run sj synth && uv run sj compile synth-session
uv run pytest
```

Roadmap and design decisions: [PLAN.md](PLAN.md).
