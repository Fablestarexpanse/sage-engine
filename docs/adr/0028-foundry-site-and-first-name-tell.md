# 0028 — Foundry site read path, and `tell` by first name

- **Status:** accepted
- **Date:** 2026-09-17
- **Supersedes:** none

## Context

M4 S4b, part 2. The Foundry read path lives in the private `Fragment-Foundary-Web-Site` repo, built on `sage registry build` (ADR 0027). The owner supplied the visual style (a mockup) and the logo.

The mockup's copy made three claims that contradict the engine:
- **"Room-based":** CLAUDE.md rule 7 says space is a graph.
- **A graphical "visual client":** the client is text in the browser.
- **LLM "narration":** models are optional, and only drive characters through player commands.

Following the site's own docs in a real run found that `tell Tamsin hello` failed. The first-party `sage.dialogue` plugin matched only a full name, and a two-word name can't be typed as one argument.

## Decision

**Site** (`Fragment-Foundary-Web-Site`, commit 5e01767).
- **Stack:** Next.js 16 static export (`output: "export"`, `trailingSlash: true`, since fragment ids contain dots), hosted on Vercel through `vercel.json`. TypeScript 5.9.3, because Next's build-time type check uses the TypeScript JavaScript API, which TypeScript 7 does not ship.
- **Pages:**
  - home, in the mockup's layout
  - about, technology, worlds
  - fragments, and one page per fragment with the install command (the registry URL filled in from the page's origin), persona, goals, voice, permissions, versions and digests
  - docs, the stranger's path
- **Registry:** `registry/inputs/` → `pnpm registry` (runs `sage registry build`) → `public/registry/`, committed, so Vercel needs no engine. `pnpm check` fails when the index is missing, wasn't built by SAGE, lists refused inputs, or is missing a listed file. Card art is copied to `public/previews/`.
- **Copy:** the mockup's claims are corrected to what the engine does. Its layout, type (Cinzel, Cormorant Garamond, Inter, Michroma) and colours are kept.
- **Placeholders:** the painted scenes are CSS gradients and SVG silhouettes until artwork exists.
- **Logo:** the owner's PNG is kept in `public/brand/logo.png`, and a trimmed 256 px copy is used. It is darkened on the parchment header, and a vector redraw is the fallback.
- **Registry contents:** `fragmentfoundry.tamsin-reed` 1.0.0 (CC0-1.0, with a card image generated for it), `sage.dialogue` and `sage.wander`.
- **Line endings:** `.gitattributes` keeps text files LF, so built registry files are identical on every machine.

**Engine: `tell` by first name.** `sage.dialogue` resolves `<name>` among the actors in the same place:
1. an exact full name, ignoring case
2. otherwise the first word of exactly one actor's name

If more than one actor matches on the first word, it answers "More than one here answers to "…"." An exact name always wins: `tell bo` reaches "Bo", not "Bo Stone". The plugin keeps version 0.1.0, since no copy of it had been published or installed anywhere but local test worlds.

## Consequences

- **Engine tests:** 1 new, 208 in total: first-word match, the ambiguous case, and exact over first word.
- **Real run:**
  - Built `out/`, served it locally, and checked every section at about 1000 px. That found and fixed:
    - sideways page overflow from the header
    - an uneven feature grid
    - inline-code styling leaking into command blocks, and the Copy button overlapping them
    - a pale logo on the parchment header
  - Then followed the docs page with a release build:
    - installed `sage.dialogue` and Tamsin by id from the served registry
    - placed Tamsin
    - ran with the plugin loaded straight from the library
    - `tell Tamsin hello` reached her, and she answered with her card's line
- **Owner actions left:**
  - Import the site repo in Vercel.
  - Replace the placeholder scenes with artwork.
  - Decide on the v0.1.0 tag.
- **Next:** S4c, the 15-minute stranger test against the deployed site and a published release.
