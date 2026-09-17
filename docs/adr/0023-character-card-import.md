# 0023 — Character card import

- **Status:** accepted
- **Date:** 2026-09-16
- **Supersedes:** none

## Context

M4 S3a. Owner rulings:
- cards come first, then packages and `sage install`
- installing and placing are separate steps
- integrity is checked by digest now, with signatures later
- SAGE's own cards will write the Tavern `chara` chunk by default

The blueprint asks that importing Tavern cards be a converter, not a new format. It also asks that the chunk parser be fuzzed: CharacterBinder v1.8 found that a crafted 32-byte PNG could hang a browser tab, because a length with the top bit set was read as negative and moved the cursor backwards.

## Decision

**`sage_schema::png`** (in `sage-schema`, so the Foundry's WASM build gets the same reader). It walks chunks without decoding pixels.
- **Lengths:** unsigned, capped at 2^31−1 as the PNG spec says, and checked against the bytes left. Each chunk moves the cursor forward by at least 12 bytes, and nothing is allocated from a length field.
- **CRC mismatches:** reported, not fatal.
- **`walk`:** stops at damage after `IHDR` and returns the chunks before it.
- **`chunks`:** strict, and used when rewriting a file.
- **`with_text_chunks`:** swaps text chunks for the later card export.
- **Text chunks:** `tEXt` and uncompressed `iTXt` are read. Compressed text (`zTXt`, or compressed `iTXt`) is never inflated.

**`sage_schema::card`** reads Tavern Card v1, v2 and v3 from PNG (`ccv3`, `chara`) or JSON. It works shape first, label second.
- **Shape decides the spec:**
  - `spec: chara_card_v3` or `chara_card_v2`
  - no `spec` but a `name` or `char_name` means v1
  - `lorebook_v3`, or a bare `entries`, is refused as a lorebook
- **Labels:** a label that disagrees with the shape is a warning, for example a v3 card under `chara`, or a v2 card under `ccv3`.
- **Both chunks present:** `ccv3` wins. A differing name in the other chunk is a warning.
- **Payload decoding:** Base64, with padding optional and whitespace ignored. Plain JSON is also accepted, with a note.
- **Limits:**
  - card payloads up to 4 MiB decoded, refused before decoding when the Base64 is already too long. Real cards with big lorebooks run to a few MiB, and SAGE's own cards will stay under 1 MiB, as the blueprint says.
  - PNG files up to 64 MiB
- **Lenient fields:** a wrong type is a warning, and that field reads as empty. Older field names (`char_persona`, `char_greeting`, `example_dialogue`, `world_scenario`) are read with a note. Lorebook entries may be a list (the card specs) or an object keyed by number (world-info exports), with `keys`/`key` and `enabled`/`disable`.
- **Report:** `CardReport {ok, source, spec, findings[{severity, path, message}], card}`, stable JSON, with findings ordered errors, then warnings, then notes. Nothing panics.

**`sage_agents::card::agent_from_card`** maps a card onto an agent as the blueprint does:

| Card field | Agent |
|---|---|
| name | `sage.describable` name: whitespace collapsed, at most 64 characters |
| description | first paragraph, at most 280 characters, as the short description others see |
| description + personality | persona, at most 4,000 characters (`sage.mind`'s limit) |
| scenario | a goal |
| `mes_example` | voice examples, split on `<START>`: at most 8, at most 1,000 characters each; `first_mes` when there are none |
| `character_book` | seed memories: enabled, non-empty entries only; at most 64, at most 1,000 characters each |

- **Macros:** `{{char}}` and `<BOT>` become the name. `{{user}}` and `<USER>` become "someone", because a shared world has no single user. Other macros stay as written, with a note.
- **Dropped with a warning:** `system_prompt` and `post_history_instructions`. SAGE builds its own prompt, and card text only ever reaches a model as contained information (ADR 0016). Alternate greetings are dropped with a note. Every shortening is a warning.
- **The agent is `hybrid`, thinking every 10 ticks.** Its rules, in order:
  1. heard `sage.said` → `@think`
  2. heard `sage.dialogue.told` → `@think`
  3. heard `sage.said` containing the agent's first name → `say <greeting>`
  4. heard `sage.dialogue.told` → `tell {speaker} <greeting>`
- **With no model,** rules 1 and 2 are skipped (ADR 0016), so the agent still answers when addressed. The greeting is the first message's quoted speech, or else its non-action text. Braces are removed and the text is cut at a sentence end within 200 characters. With no spoken line, rules 3 and 4 are left out, with a note.

**`sage.mind` v3** adds `voice`: at most 8 examples, each at most 1,000 characters. LLM drivers add each one to the prompt as a contained `Voice example:` line. The v2→v3 upcaster only checks that the data is an object; `voice` defaults to empty.

**`sage card <card.png|card.json>`** prints one line of JSON: `{ok, source, spec, findings, agent}`. Findings from reading and from converting are merged. It exits non-zero when the card isn't usable. It writes nothing; placing an agent in a world is S3b. A file named `.png`, or starting with the PNG signature, is read as PNG, and anything else as JSON.

**Fuzzing.**
- **Stable-toolchain test:** 20,000 fixed-seed mutations of valid cards (bit flips, random bytes, truncation, extreme length fields, duplicated and deleted spans). No read may panic or take 250 ms.
- **Coverage-guided fuzzer:** `crates/sage-schema/fuzz` (cargo-fuzz, target `read_card`, with seeds and a dictionary). It runs for 3 minutes in a CI job on nightly Linux. It is its own workspace, so libfuzzer stays out of the engine build.

## Consequences

- **Tests:** 27 new, 186 in total.
  - PNG unit tests: CRC against the spec values, reading and rewriting, `iTXt`, hostile lengths including the CharacterBinder case, and bad CRCs.
  - 12 card tests: v2 with lorebook, `ccv3` precedence, label and shape mismatches, v1 and old names, UTF-8 through Base64, non-cards, wrong types, world-info entries, oversize, stable JSON, cut-off files, and mutations.
  - Converter tests: the mapping, and every loss reported; the card's `system_prompt` appears nowhere in the agent.
  - Oversized cards are cut to what a mind accepts.
  - An imported agent in a real world with no model answers when addressed by name and stays quiet otherwise.
  - A v2 mind in the log upcasts, and an over-long voice example is refused.
  - `sage card` against the binary.
  - The LLM prompt test now checks that voice examples appear, contained.
- **Real run:**
  - I wrote a card with CharacterBinder's own PNG encoder, run under Node from its source: a v2 card with a lorebook (one entry disabled), a `system_prompt` and an alternate greeting, on its 2.2 MB logo. CharacterBinder read it back.
  - `sage card` read it in 0.1 s (debug build) and reported exactly the three losses.
  - A copy cut at 1 MB still gave the agent, with a damage warning.
  - The 32-byte hang case was refused at once.
- **Bugs found by the real run:**
  - A first message with speech split by an action gave the greeting `Fog's extra." "Name?`. Now only the quoted speech is used.
  - A cut-off download was refused although the whole card came before the damage. Now the chunks before the damage are read, with a warning.
- **Not verified yet:**
  - a card written by SillyTavern or Chub themselves (none available offline)
- **Fuzzing result:** the first CI fuzz run executed 8,105,184 inputs in 181 s (coverage 1,959 edges, 1,946 corpus entries), with no crash, hang or out-of-memory. The first attempt never fuzzed at all: `rust-toolchain.toml` overrode nightly, and the job now runs `cargo +nightly fuzz`.
- **Not built yet:**
  - placing an imported agent with its seed memories, and exporting SAGE cards with `chara` and `sage` chunks (S3b)
  - lorebooks as their own fragments
  - Tavern extensions
- **Next:** S3b, `.sagepkg` and `sage install` into a world's fragment library, and a placement step that commits the agent and its seed memories as events.
