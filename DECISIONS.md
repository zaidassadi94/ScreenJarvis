# Decisions & deferred work

A running log of the product/architecture calls behind ScreenJarvis, and the
things deliberately left for later. Newest section on top. See `PLAN.md` for the
roadmap and `HANDOFF.md` for the live session state.

---

## 2026-07-14 — Installable app + usable output

The two questions this round answered: *how do people install it* and *how does
the output become something you actually use*. Three product decisions, taken
with the project owner:

### D1 — Default action on release: **auto-paste text (Wispr-style)**

When you release the key, the cleaned narration is pasted straight into whatever
text box has focus (⌘V into the frontmost app), exactly like Wispr Flow. The
figures still land in the session doc for when you want them.

- Every other hand-off is available on demand, selectable via `on_done`:
  `paste-text` (default) · `copy-text` · `copy-rich` · `open-html` ·
  `claude-prompt` (the old default) · `path` · `off`.
- The menu-bar app exposes the non-paste variants directly (Copy Text / Copy
  Rich Text / Open as Web Page / Copy Claude Prompt). A *menu* "paste" is
  intentionally absent: clicking a menu item moves focus, so the ⌘V would land
  in the wrong place. Auto-paste only runs on release, when the target app is
  focused.
- Config key renamed `copy_on_done` → `on_done` (it no longer only copies). The
  old name is still read for back-compat (`config.load_config`).
- Code: `app/controller.py::_hand_off`, `app/notify.py` (macOS verbs),
  `compiler/deliver.py` (content).

### D2 — Images: **embed now, host later**

Screenshots are embedded (data URIs in HTML; RTF-embedded images in the rich
clipboard). Self-contained, offline, no account, nothing leaves the machine.

- The single seam for a future hosting backend is `deliver._image_src`, gated by
  `Config.image_hosting` (only `"embed"` today). A backend would upload figures
  and return URLs there, so plain-text destinations could carry links.
- **Deferred:** actual object-storage upload (S3 / Cloudflare R2 / gist). Needs a
  bucket + credentials from the owner; not built until then.

### D3 — Document formats: **HTML now; Markdown & PDF deferred**

The "feedback document" use case ships as a **single self-contained HTML page**
(`compiler/deliver.py::session_html`, `sj export --format html`): images
embedded, styled, light/dark aware, and "Print → Save as PDF" gives a clean PDF
with zero extra dependencies.

- **Deferred — portable Markdown:** a single `.md` with data-URI images. Owner
  wants to revisit the exact shape (data-URI vs. bundled `images/` vs. a
  hosted-URL variant), so it's not built yet. `sj export --format text` already
  gives plain narration; a `--format md` slots in next to it.
- **Deferred — PDF:** direct PDF generation (would add `fpdf2` or similar). HTML
  → system "Print to PDF" covers the need for now, so the dependency isn't
  justified yet.

### D4 — Packaging: **py2app `.app` + `.dmg`, menu-bar accessory**

`sj app` from Terminal → a double-clickable **ScreenJarvis.app**
(`packaging/`, `scripts/build_app.sh`, `packaging/BUILD.md`).

- `LSUIElement` accessory: no Dock icon, never steals focus (required for
  auto-paste to work). Info.plist carries the mic + AppleEvents usage strings so
  prompts read well and TCC grants attach to *ScreenJarvis*, not Terminal.
- First run needs **no terminal**: the menu's **Set API Keys…** collects keys
  via a native dialog (`notify.prompt_secret`) and saves them with the existing
  line-preserving TOML merge (`setup_wizard.save_keys`).
- **Not** a Mac App Store build: global hotkey capture, screen recording, and
  synthetic paste keystrokes are incompatible with the App Sandbox — this is a
  Developer-ID-signed app for direct download. Signing/notarization is wired into
  the build script behind `SJ_SIGN_IDENTITY` / `SJ_NOTARY_PROFILE`.
- **Deferred — signed public release:** the build produces an *unsigned* app here
  (no Apple Developer account in the loop yet). Producing a notarized `.dmg` for
  others to download is a follow-up once the owner has a Developer ID.
- **Deferred — Terminal-free build:** building the app still requires running
  `scripts/build_app.sh` on a Mac. A CI job (GitHub Actions macOS runner) that
  builds + notarizes on tag is the natural next step.

---

## Earlier

See git history and `PLAN.md` for the pre-existing calls: recorder/compiler
split, cloud STT with a local privacy toggle, smart/basic dual interpreter with
automatic fallback, config-file keys authoritative over stale shell env.
