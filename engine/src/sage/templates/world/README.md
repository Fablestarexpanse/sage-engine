# __WORLD_NAME__

A SAGE world package, made with `sage world new __WORLD_ID__`. It has one room and no map yet.

## Next steps

1. **Draw the map in WorldForge.** Open the repository root in WorldForge, pick this world, and
   add rooms around `start:arrival` in the `start` zone. Connect exits, write descriptions, save.
2. **Check it:** `python -m sage validate --world __WORLD_ID__`
3. **Play it:** `sage quickstart --world __WORLD_ID__`, then open http://localhost:8001/ and press
   **Play**. Saves in WorldForge reload into the running server.

## What each file is for

| File | Holds |
|---|---|
| `world.toml` | id, name, start and respawn room, room types and exit directions WorldForge offers, plugins, params |
| `stats.yaml` | attributes, vitals and the character-creation point budget |
| `currencies.yaml` | in-world money |
| `lexicon/en.yaml` | every word players see that this world changes: banner, message of the day, stat and currency names |
| `content/world/zones/` | zones and their rooms (drawn in WorldForge) |
| `content/world/entities/`, `items/` | creature and item templates |
| `ai/style.yaml` | tone and rules for optional AI narration; add `ai/prompts/narrate.room.j2` to turn it on |
| `ui/theme.yaml` | the player client's mark and accent colour |
| `content.schema.json` | the fields editors offer, from the engine and enabled plugins (`python -m sage schema export --world __WORLD_ID__ --out worlds/__WORLD_ID__/content.schema.json`) |

Turning on a mechanic: uncomment a plugin in `world.toml`, run
`python -m sage db upgrade --world __WORLD_ID__`, re-export the schema, and restart.
