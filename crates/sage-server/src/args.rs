//! Command-line parsing. Small enough that a parser crate would cost more than it saves.

use std::path::PathBuf;

pub enum Command {
    Version,
    Help,
    Run(Box<RunOptions>),
    Inspect {
        world: PathBuf,
    },
    Check {
        fragment: PathBuf,
    },
    Card {
        file: PathBuf,
    },
    Install {
        world: PathBuf,
        /// A path, or an `https://` URL.
        source: String,
        options: crate::library::CardOptions,
        digest: Option<String>,
        registry: Option<String>,
    },
    RegistryBuild {
        inputs: PathBuf,
        out: PathBuf,
    },
    Place {
        world: PathBuf,
        fragment: String,
        options: crate::place::PlaceOptions,
    },
    Pack {
        fragment: PathBuf,
        out: PathBuf,
    },
    Export {
        world: PathBuf,
        fragment: String,
        out: PathBuf,
    },
}

#[derive(Debug, PartialEq)]
pub struct RunOptions {
    pub world: PathBuf,
    pub seed: Option<PathBuf>,
    pub hz: u32,
    pub until_tick: Option<u64>,
    pub snapshot_every: u64,
    pub checkpoint_every: u64,
    pub plugins: Vec<PathBuf>,
    pub report_every: u64,
    pub llm_url: Option<String>,
    pub llm_model: Option<String>,
    pub llm_workers: usize,
    pub embed_url: Option<String>,
    pub embed_model: Option<String>,
    pub listen: Option<String>,
    pub start_place: Option<u64>,
}

pub struct Args {
    pub command: Command,
}

impl Args {
    pub fn parse(mut args: impl Iterator<Item = String>) -> Result<Args, String> {
        let command = match args.next().as_deref() {
            None | Some("--version") | Some("-V") => Command::Version,
            Some("--help") | Some("-h") | Some("help") => Command::Help,
            Some("inspect") => {
                let world = args.next().ok_or("inspect needs a world file")?;
                if let Some(extra) = args.next() {
                    return Err(format!("unexpected argument `{extra}`"));
                }
                Command::Inspect {
                    world: world.into(),
                }
            }
            Some("check") => {
                let fragment = args.next().ok_or("check needs a fragment directory")?;
                if let Some(extra) = args.next() {
                    return Err(format!("unexpected argument `{extra}`"));
                }
                Command::Check {
                    fragment: fragment.into(),
                }
            }
            Some("card") => {
                let file = args.next().ok_or("card needs a PNG or JSON card file")?;
                if let Some(extra) = args.next() {
                    return Err(format!("unexpected argument `{extra}`"));
                }
                Command::Card { file: file.into() }
            }
            Some("install") => {
                let mut positional = Vec::new();
                let mut options = crate::library::CardOptions::default();
                let mut digest = None;
                let mut registry = None;
                while let Some(arg) = args.next() {
                    let mut value = || args.next().ok_or_else(|| format!("{arg} needs a value"));
                    match arg.as_str() {
                        "--id" => options.id = Some(value()?),
                        "--version" => options.version = Some(value()?),
                        "--license" => options.license = Some(value()?),
                        "--digest" => digest = Some(value()?),
                        "--registry" => registry = Some(value()?),
                        _ if arg.starts_with("--") => {
                            return Err(format!("unknown option `{arg}`"));
                        }
                        _ => positional.push(arg),
                    }
                }
                let [world, source]: [String; 2] = positional.try_into().map_err(
                    |_| "install needs a world file and a fragment directory, package, card file or URL",
                )?;
                Command::Install {
                    world: world.into(),
                    source,
                    options,
                    digest,
                    registry,
                }
            }
            Some("registry") => {
                let (Some(action), Some(inputs), Some(out), None) =
                    (args.next(), args.next(), args.next(), args.next())
                else {
                    return Err(
                        "registry build needs an inputs directory and an output directory".into(),
                    );
                };
                if action != "build" {
                    return Err(format!("unknown registry action `{action}`"));
                }
                Command::RegistryBuild {
                    inputs: inputs.into(),
                    out: out.into(),
                }
            }
            Some("pack") => {
                let (Some(fragment), Some(out), None) = (args.next(), args.next(), args.next())
                else {
                    return Err(
                        "pack needs a fragment directory and an output .sagepkg file".into(),
                    );
                };
                Command::Pack {
                    fragment: fragment.into(),
                    out: out.into(),
                }
            }
            Some("export") => {
                let (Some(world), Some(fragment), Some(out), None) =
                    (args.next(), args.next(), args.next(), args.next())
                else {
                    return Err(
                        "export needs a world file, an installed fragment id and an output .png file"
                            .into(),
                    );
                };
                Command::Export {
                    world: world.into(),
                    fragment,
                    out: out.into(),
                }
            }
            Some("place") => {
                let mut positional = Vec::new();
                let mut options = crate::place::PlaceOptions::default();
                while let Some(arg) = args.next() {
                    let mut value = || args.next().ok_or_else(|| format!("{arg} needs a value"));
                    match arg.as_str() {
                        "--at" => options.at = Some(number(&arg, &value()?)?),
                        "--name" => options.name = Some(value()?),
                        _ if arg.starts_with("--") => {
                            return Err(format!("unknown option `{arg}`"));
                        }
                        _ => positional.push(arg),
                    }
                }
                let [world, fragment]: [String; 2] = positional
                    .try_into()
                    .map_err(|_| "place needs a world file and an installed fragment id")?;
                Command::Place {
                    world: world.into(),
                    fragment,
                    options,
                }
            }
            Some("run") => Command::Run(Box::new(parse_run(args)?)),
            Some(other) => return Err(format!("unknown command `{other}`")),
        };
        Ok(Args { command })
    }
}

fn parse_run(mut args: impl Iterator<Item = String>) -> Result<RunOptions, String> {
    let mut world = None;
    let mut options = RunOptions {
        world: PathBuf::new(),
        seed: None,
        hz: 4,
        until_tick: None,
        snapshot_every: 2400,
        checkpoint_every: 240,
        plugins: Vec::new(),
        report_every: 240,
        llm_url: None,
        llm_model: None,
        llm_workers: 2,
        embed_url: None,
        embed_model: None,
        listen: None,
        start_place: None,
    };
    while let Some(arg) = args.next() {
        if !arg.starts_with("--") {
            if world.replace(PathBuf::from(&arg)).is_some() {
                return Err(format!("unexpected argument `{arg}`"));
            }
            continue;
        }
        let mut value = || args.next().ok_or_else(|| format!("{arg} needs a value"));
        match arg.as_str() {
            "--seed" => options.seed = Some(value()?.into()),
            "--hz" => options.hz = number(&arg, &value()?)?,
            "--until-tick" => options.until_tick = Some(number(&arg, &value()?)?),
            "--snapshot-every" => options.snapshot_every = positive(&arg, &value()?)?,
            "--checkpoint-every" => options.checkpoint_every = positive(&arg, &value()?)?,
            "--plugin" => options.plugins.push(value()?.into()),
            "--report-every" => options.report_every = positive(&arg, &value()?)?,
            "--llm-url" => options.llm_url = Some(value()?),
            "--llm-model" => options.llm_model = Some(value()?),
            "--embed-url" => options.embed_url = Some(value()?),
            "--embed-model" => options.embed_model = Some(value()?),
            "--listen" => options.listen = Some(value()?),
            "--start-place" => options.start_place = Some(number(&arg, &value()?)?),
            "--llm-workers" => {
                options.llm_workers = usize::try_from(positive(&arg, &value()?)?)
                    .map_err(|_| format!("{arg} is too large"))?
            }
            _ => return Err(format!("unknown option `{arg}`")),
        }
    }
    options.world = world.ok_or("run needs a world file")?;
    if options.llm_url.is_some() != options.llm_model.is_some() {
        return Err("--llm-url and --llm-model go together".into());
    }
    if options.embed_url.is_some() != options.embed_model.is_some() {
        return Err("--embed-url and --embed-model go together".into());
    }
    if options.embed_url.is_some() && options.llm_url.is_none() {
        return Err(
            "--embed-url only matters with --llm-url: embeddings choose what a model sees".into(),
        );
    }
    Ok(options)
}

fn number<T: std::str::FromStr>(flag: &str, value: &str) -> Result<T, String> {
    value
        .parse()
        .map_err(|_| format!("{flag} expects a whole number, got `{value}`"))
}

fn positive(flag: &str, value: &str) -> Result<u64, String> {
    match number(flag, value)? {
        0 => Err(format!("{flag} must be at least 1")),
        n => Ok(n),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn run(args: &[&str]) -> Result<RunOptions, String> {
        match Args::parse(args.iter().map(|s| s.to_string()))?.command {
            Command::Run(options) => Ok(*options),
            _ => Err("not a run command".into()),
        }
    }

    #[test]
    fn run_defaults() {
        let options = run(&["run", "w.db"]).unwrap();
        assert_eq!(options.world, PathBuf::from("w.db"));
        assert_eq!((options.hz, options.snapshot_every), (4, 2400));
        assert!(options.plugins.is_empty());
    }

    #[test]
    fn run_flags_in_any_order() {
        let options = run(&["run", "--hz", "0", "w.db", "--until-tick", "50"]).unwrap();
        assert_eq!((options.hz, options.until_tick), (0, Some(50)));
    }

    #[test]
    fn llm_options_come_as_a_pair() {
        let options = run(&[
            "run",
            "w.db",
            "--llm-url",
            "http://localhost:11434/v1",
            "--llm-model",
            "llama3.2",
        ])
        .unwrap();
        assert_eq!(options.llm_model.as_deref(), Some("llama3.2"));
        assert_eq!(options.llm_workers, 2);
        assert!(run(&["run", "w.db", "--llm-url", "http://x/v1"]).is_err());
        assert!(run(&["run", "w.db", "--llm-model", "m"]).is_err());
        assert!(run(&["run", "w.db", "--embed-url", "u", "--embed-model", "e"]).is_err());
        assert!(
            run(&[
                "run",
                "w.db",
                "--llm-url",
                "u",
                "--llm-model",
                "m",
                "--embed-url",
                "u"
            ])
            .is_err()
        );
        let both = run(&[
            "run",
            "w.db",
            "--llm-url",
            "u",
            "--llm-model",
            "m",
            "--embed-url",
            "u",
            "--embed-model",
            "e",
        ])
        .unwrap();
        assert_eq!(both.embed_model.as_deref(), Some("e"));
        assert!(
            run(&[
                "run",
                "w.db",
                "--llm-model",
                "m",
                "--llm-url",
                "u",
                "--llm-workers",
                "0"
            ])
            .is_err()
        );
    }

    #[test]
    fn plugins_keep_their_order() {
        let options = run(&["run", "w.db", "--plugin", "b", "--plugin", "a"]).unwrap();
        assert_eq!(options.plugins, [PathBuf::from("b"), PathBuf::from("a")]);
    }

    #[test]
    fn refuses_bad_input() {
        assert!(run(&["run"]).is_err());
        assert!(run(&["run", "a.db", "b.db"]).is_err());
        assert!(run(&["run", "w.db", "--hz"]).is_err());
        assert!(run(&["run", "w.db", "--hz", "fast"]).is_err());
        assert!(run(&["run", "w.db", "--snapshot-every", "0"]).is_err());
        assert!(run(&["run", "w.db", "--turbo"]).is_err());
    }
}
