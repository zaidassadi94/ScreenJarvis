# ScreenJarvis — Session Handoff (2026-07-15)

## ⚠️ ACTION REQUIRED FIRST — rotate exposed API keys (NOT YET DONE)

In the last session a `grep` of `~/.zshrc` printed the **live Groq and Anthropic
API keys** into the chat. Any secret pasted into a chat/log/screenshot must be
treated as compromised. **As of this handoff they have NOT been rotated.** An
exposed Anthropic key can incur charges — do this before anything else:

- [ ] **Anthropic:** console.anthropic.com → Settings → API Keys → delete the old key → **Create Key**
- [ ] **Groq:** console.groq.com → API Keys → delete the old key → **Create API Key**
- [ ] `cd ScreenJarvis && uv run sj setup` → paste the **new** keys (these are now authoritative — no `unset` needed)
- [ ] Optional shell tidy (removes the now-dead exports, backup first):
      `cp ~/.zshrc ~/.zshrc.backup && sed -i '' '/API_KEY/d' ~/.zshrc`
- [ ] Delete this section once the keys are rotated.

Never paste a raw key again — to inspect one safely, print length + first/last
few chars only.

---

## Status: working end-to-end on macOS 🎉

The full Wispr-style loop runs on real hardware. Confirmed in the last session:
a ~90s recording compiled in **smart mode** (`claude-opus-4-8`) into a document
with 9 Claude-written figure captions (e.g. *"Get early access button blending
into the header"*, *"Wispr Flow's integrations showcase"*).

### What works
- **Record:** hold right-Option anywhere → talk + point/click/circle → release.
- **Compile:** Groq/OpenAI transcription (word-timestamped) → gesture detection →
  Claude "understanding" pass → annotated `transcript.md` + `images/`. Falls back
  to offline **basic** mode automatically if Claude/key fails — a recording is
  never lost.
- **Menu-bar app** (`sj app`): resident hold-to-talk, background compile queue,
  notification, clipboard hand-off, start-at-login.
- **Keys:** `sj setup` values are now authoritative over stale shell env vars
  (the bug that cost ~a dozen debugging rounds — fixed in commit 37581e7).

### Known issues / next up (in priority order)
1. **Smart mode over-includes figures** — 9 for a ~90s clip is too many. Tune the
   understanding prompt / add a max-figures cap (config `max_llm_frames` bounds
   input frames, not output figures — the prompt should be told to be selective).
   This is the clear next task; the user flagged "not everything was perfect."
2. **macOS notifications may be suppressed** (Focus mode / permission) — cosmetic;
   the compile still succeeds and the doc/clipboard are correct.
3. Basic-mode rings were "ok, not perfect" — largely superseded by smart mode.

### How to run
```sh
cd ScreenJarvis
uv sync
uv run sj setup            # one-time: API keys, hotkey, prefs
uv run sj app              # menu-bar app (macOS)
uv run sj compile last     # (re)compile the latest recording; shows progress
uv run sj last --open      # open the latest session folder
uv run pytest -q           # 53 tests, all green
uv run sj synth && uv run sj compile synth-session   # headless demo, no mic/screen
```

### Repo
- Branch: `claude/wispr-screen-context-tool-4eg3bz`
- Latest before this handoff: `37581e7` (config-authoritative keys)
- Architecture and roadmap: `PLAN.md`. Project guide for future sessions: `CLAUDE.md`.
