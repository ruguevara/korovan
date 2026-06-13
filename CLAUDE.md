# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A single-page meme site ("КОРОВАН") hosted on GitHub Pages. It shows the classic
Kirill copypasta about wanting a game, plus a live counter of how many years he's
been waiting. Counting starts **1999-11-26** (hardcoded as `START` in `index.html`).

There is no build step, no framework, no dependencies. Everything — markup, CSS, and
JS — lives inline in `index.html`. Edit that one file.

## Commands

- Preview locally: `python3 -m http.server 8000` then open `http://localhost:8000`
  (or just open `index.html` directly).
- No build, lint, or test tooling — deployment is a `git push` to `main` (GitHub Pages
  serves the repo root).

## Key details

- The counter logic uses Russian pluralization (`pluralRu`) for год/года/лет and
  день/дня/дней — keep that intact when touching the counter, it's the easy thing to break.
- Years are counted by calendar (anniversary check), not by dividing milliseconds, so
  leap years stay correct.
- `.nojekyll` disables Jekyll processing — leave it in place.
- `CNAME` holds the single canonical custom domain (`korovan.ru`). GitHub Pages allows
  only one custom domain per repo; the second domain `kopobah.ru` ("korovan" in the
  Russian keyboard layout) is a Cloudflare redirect to it, not a separate Pages site.
  See `README.md` for the full Cloudflare DNS + redirect setup.
- Page is Russian (`lang="ru"`); the copypasta is intentionally kept with its original
  misspellings — do not "fix" them.
