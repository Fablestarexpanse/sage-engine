//! The `sage` binary.
//!
//! `sage run` drives a world stored in one SQLite file at a fixed tick rate. `sage inspect`
//! reports on a world file and checks that its newest snapshot agrees with a full replay.
//! `sage check` reports whether this engine can use a fragment. `sage card` reads a Tavern
//! character card and shows the agent it becomes. `sage install` adds a verified fragment to
//! a world's library, and `sage place` puts an installed agent into a stopped world. `sage pack`
//! writes a fragment as a `.sagepkg`, and `sage export` writes an installed agent as a SAGE card.

mod accounts;
mod args;
mod card;
mod check;
mod download;
mod export;
mod library;
mod net;
mod package;
mod place;
mod players;
mod protocol;
mod registry;
mod run;
mod web;

use std::process::ExitCode;

use args::{Args, Command};

const USAGE: &str = "\
usage:
  sage --version
  sage run <world.db> [options]
      --seed <file>              seed a new, empty world from a sage.seed/1 file
      --hz <n>                   ticks per second; 0 runs as fast as possible (default 4)
      --until-tick <n>           stop cleanly once this tick has run
      --snapshot-every <ticks>   save a snapshot this often (default 2400)
      --checkpoint-every <ticks> record idle clock time this often (default 240)
      --plugin <fragment-dir>    load a plugin after `sage check` passes; repeatable, runs in order
      --report-every <ticks>     print a status line this often (default 240)
      --llm-url <url>            OpenAI-compatible API for llm and hybrid agents, e.g. http://localhost:11434/v1
      --llm-model <name>         model to ask; required with --llm-url (key, if any, from SAGE_LLM_API_KEY)
      --llm-workers <n>          concurrent model requests (default 2)
      --embed-url <url>          OpenAI-compatible embeddings API for memory relevance (needs --llm-url)
      --embed-model <name>       embedding model, e.g. nomic-embed-text; cache in <world>.embeddings.db
      --listen <addr>            accept players over WebSocket at ws://<addr>/ws, e.g. 127.0.0.1:4700
      --start-place <id>         where new characters start (default: the lowest-numbered place)
  sage inspect <world.db>
  sage check <fragment-dir>       validate fragment.yaml and, for plugins, plugin.wasm
  sage card <card.png|card.json>  read a Tavern character card and show the agent it becomes
  sage pack <fragment-dir> <out.sagepkg>
                                  check a fragment and write it as one .sagepkg file
  sage install <world.db> <fragment-dir|package.sagepkg|card.png|card.json|https-url> [options]
                                  verify a fragment and add it to <world.db>.fragments/
      --digest <sha256:...>      refuse unless the content has exactly this digest
      --registry <url>           install <id>[@<version requirement>] from a registry, e.g. a Foundry
  sage registry build <inputs-dir> <out-dir>
                                  verify .sagepkg files, SAGE cards and fragment directories and
                                  write a static registry (index.json, api/v1, blobs by digest)
      --id <creator.slug>        card files: fragment id (default local.<name>)
      --version <semver>         card files: version (default the card's, else 0.1.0)
      --license <spdx>           card files: license (default LicenseRef-Unspecified)
  sage place <world.db> <id>[@version] [--at <place-id>] [--name <name>]
                                  put an installed agent into a stopped world
  sage export <world.db> <id>[@version] <out.png>
                                  write an installed agent as a SAGE card (Tavern-readable)";

fn main() -> ExitCode {
    let args = match Args::parse(std::env::args().skip(1)) {
        Ok(args) => args,
        Err(message) => {
            eprintln!("sage: {message}\n\n{USAGE}");
            return ExitCode::from(2);
        }
    };
    let result = match args.command {
        Command::Version => {
            println!("sage {}", env!("CARGO_PKG_VERSION"));
            Ok(())
        }
        Command::Help => {
            println!("{USAGE}");
            Ok(())
        }
        Command::Run(options) => run::run(&options),
        Command::Inspect { world } => run::inspect(&world),
        Command::Check { fragment } => check::run(&fragment),
        Command::Card { file } => card::run(&file),
        Command::Install {
            world,
            source,
            options,
            digest,
            registry,
        } => library::run(
            &world,
            &source,
            &options,
            digest.as_deref(),
            registry.as_deref(),
        ),
        Command::RegistryBuild { inputs, out } => registry::build(&inputs, &out),
        Command::Place {
            world,
            fragment,
            options,
        } => place::run(&world, &fragment, &options),
        Command::Pack { fragment, out } => package::run(&fragment, &out),
        Command::Export {
            world,
            fragment,
            out,
        } => export::run(&world, &fragment, &out),
    };
    match result {
        Ok(()) => ExitCode::SUCCESS,
        Err(message) => {
            eprintln!("sage: {message}");
            ExitCode::FAILURE
        }
    }
}
