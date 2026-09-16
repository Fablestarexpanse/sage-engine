//! The `sage` binary.
//!
//! `sage run` drives a world stored in one SQLite file at a fixed tick rate. `sage inspect`
//! reports on a world file and checks that its newest snapshot agrees with a full replay.
//! `sage check` reports whether this engine can use a fragment.
//! Network transport arrives at M4.

mod args;
mod check;
mod run;

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
  sage inspect <world.db>
  sage check <fragment-dir>       validate fragment.yaml and, for plugins, plugin.wasm";

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
    };
    match result {
        Ok(()) => ExitCode::SUCCESS,
        Err(message) => {
            eprintln!("sage: {message}");
            ExitCode::FAILURE
        }
    }
}
