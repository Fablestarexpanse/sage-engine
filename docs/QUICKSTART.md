# SAGE quickstart

SAGE is a text-world engine: places joined by ways, characters who act only through the commands a player could type, and agents that remember what they perceived. This gets you from download to playing in a browser.

## 1. Download

Get the archive for your computer from the [releases page](https://github.com/Fablestarexpanse/sage-engine/releases), and check it against `SHA256SUMS`:

| Computer | Archive |
|---|---|
| Windows | `sage-v…-x86_64-pc-windows-msvc.zip` |
| Mac with Apple silicon | `sage-v…-aarch64-apple-darwin.tar.gz` |
| Mac with Intel | `sage-v…-x86_64-apple-darwin.tar.gz` |
| Linux | `sage-v…-x86_64-unknown-linux-gnu.tar.gz` |

Unpack it and open a terminal in the unpacked folder.

- **Windows:** use `sage.exe` in place of `./sage` below. SmartScreen may warn about an unsigned app; choose "More info", then "Run anyway".
- **macOS:** the binary is not notarized yet. Clear the download flag once, with `xattr -d com.apple.quarantine sage`.

## 2. Start a world

```bash
./sage run my-world.db --seed worlds/demo-agents/seed.json --plugin plugins/sage.dialogue --listen 127.0.0.1:4700
```

- `--seed` fills a new, empty world, here with a few places and ten agents that follow simple rules.
- `--plugin` adds `tell`, which lets you speak to one character.
- `--listen` lets you play at <http://127.0.0.1:4700/>.

Everything that happens is recorded in `my-world.db`, and stopping with Ctrl-C loses nothing. Next time, run the same command without `--seed`.

## 3. Play

Open <http://127.0.0.1:4700/>, choose **Create a character**, and pick a name and password. Then type:

- `look`: where you are, the ways on, and who is here
- `say hello`: everyone here hears you
- `onward`, or `go onward`: take a way out by its name
- `emote waves`: an action others see
- `tell Ada hello`: speak to one character

Up and down arrows recall earlier commands.

## 4. Bring a character in

Any Tavern character card (a PNG from a character card site or card editor, or its JSON) can join your world. Stop the world first (Ctrl-C), then:

```bash
./sage card my-character.png
./sage install my-world.db my-character.png --license CC-BY-4.0
./sage place my-world.db local.my-character
```

1. `sage card` shows what the character becomes, and anything left behind (SAGE writes its own prompts, so a card's system prompt isn't used).
2. `sage install` adds the card to the world's library.
3. `sage place` puts the character in the first place. The id is `local.` plus the name in lowercase with hyphens, as `sage install` prints it.

Start the world again and say the character's name. Fragments can also be installed from a web address, pinned to their exact content:

```bash
./sage install my-world.db https://example.com/some.sagepkg --digest sha256:…
```

## 5. Let characters think (optional)

With no model, characters follow their rules and answer with a line from their card. To let them think, point SAGE at any OpenAI-compatible endpoint, such as [Ollama](https://ollama.com) running on your machine:

```bash
./sage run my-world.db --plugin plugins/sage.dialogue --listen 127.0.0.1:4700 \
  --llm-url http://localhost:11434/v1 --llm-model llama3.2
```

If the endpoint needs a key, set `SAGE_LLM_API_KEY`. Whatever a model answers, a character can still only do what a player could type.

## Help

`./sage --help` lists every command. Report problems at <https://github.com/Fablestarexpanse/sage-engine/issues>.
