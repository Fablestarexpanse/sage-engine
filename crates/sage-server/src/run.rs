//! `sage run` and `sage inspect`.

use std::path::Path;
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::{Duration, Instant};

use sage_agents::Agents;
use sage_agents::embeddings::{EmbeddingCache, HttpEmbedder, Relevance};
use sage_agents::llm::{HttpTransport, LlmConfig, Thinker};
use sage_core::{Journal, Scheduler, SnapshotEntity, Upcasters, entities_to_events};
use sage_host::{Limits, PluginHost, PluginSystem};
use sage_store::SqliteLog;

use crate::args::RunOptions;

const SEED_SCHEMA: &str = "sage.seed/1";

/// Held while a process may write a world: an exclusive OS lock on `<world>.lock`. The
/// operating system releases it when the process ends, however it ends. The log's own sequence
/// check would stop a second writer only at its next append, after the running world had
/// already diverged; this refuses it before anything is read or written.
pub(crate) struct WriterLock {
    _file: std::fs::File,
}

pub(crate) fn lock_for_writing(world: &Path) -> Result<WriterLock, String> {
    let mut name = world.as_os_str().to_owned();
    name.push(".lock");
    let path = std::path::PathBuf::from(name);
    let file = std::fs::OpenOptions::new()
        .create(true)
        .truncate(false)
        .write(true)
        .open(&path)
        .map_err(|e| format!("{}: {e}", path.display()))?;
    match file.try_lock() {
        Ok(()) => Ok(WriterLock { _file: file }),
        Err(std::fs::TryLockError::WouldBlock) => Err(format!(
            "{} is in use by another sage process; stop the running world first",
            world.display()
        )),
        Err(std::fs::TryLockError::Error(e)) => Err(format!("{}: {e}", path.display())),
    }
}

/// Opens a world for writing: takes the writer lock, then the journal.
pub(crate) fn open_for_writing(path: &Path) -> Result<(Journal<SqliteLog>, WriterLock), String> {
    let lock = lock_for_writing(path)?;
    Ok((open(path)?, lock))
}

/// Asks the model for a one-word reply on a background thread, so a local server loads the
/// model before the first agent needs it, and reports how long that took or why it failed.
fn warm_up(config: LlmConfig) {
    use sage_agents::llm::{HttpTransport, Message, Transport};
    std::thread::spawn(move || {
        let started = std::time::Instant::now();
        let transport = HttpTransport::new(config);
        let reply = transport.complete(
            &[Message {
                role: "user",
                content: "Reply with the word ready.".into(),
            }],
            &serde_json::json!({"type": "text"}),
        );
        match reply {
            Ok(_) => println!("llm ready in {} ms", started.elapsed().as_millis()),
            Err(e) => eprintln!("llm warm-up failed: {e}"),
        }
    });
}

fn open(path: &Path) -> Result<Journal<SqliteLog>, String> {
    let log = SqliteLog::open(path).map_err(|e| format!("{}: {e}", path.display()))?;
    Journal::open(log, sage_agents::registry(), Upcasters::core())
        .map_err(|e| format!("{}: {e}", path.display()))
}

/// Reads a `sage.seed/1` file: `{"schema": "sage.seed/1", "entities": [...]}`, where entities
/// use the snapshot entity shape.
fn read_seed(path: &Path) -> Result<Vec<SnapshotEntity>, String> {
    let fail = |e: &dyn std::fmt::Display| format!("seed {}: {e}", path.display());
    let text = std::fs::read_to_string(path).map_err(|e| fail(&e))?;
    let mut value: serde_json::Value = serde_json::from_str(&text).map_err(|e| fail(&e))?;
    match value.get("schema").and_then(|s| s.as_str()) {
        Some(SEED_SCHEMA) => {}
        other => {
            return Err(fail(&format!(
                "schema is {other:?}, expected \"{SEED_SCHEMA}\""
            )));
        }
    }
    serde_json::from_value(value["entities"].take()).map_err(|e| fail(&e))
}

pub fn run(options: &RunOptions) -> Result<(), String> {
    // Plugins are checked and loaded before the world file is touched, so a refused plugin
    // leaves no trace.
    let mut plugins = Vec::new();
    let mut lexicon = sage_agents::lexicon_english();
    if !options.plugins.is_empty() {
        let host = PluginHost::new().map_err(|e| e.to_string())?;
        for dir in &options.plugins {
            let plugin = load_checked_plugin(&host, dir)?;
            for (key, template) in plugin.lexicon() {
                lexicon.set(key, template);
            }
            plugins.push(plugin);
        }
    }

    let (mut journal, _lock) = open_for_writing(&options.world)?;

    if let Some(seed) = &options.seed {
        if !journal.world().is_empty() || journal.world().last_seq() > 0 {
            return Err(format!(
                "{} already has a history; --seed only applies to a new world",
                options.world.display()
            ));
        }
        let events = entities_to_events(&read_seed(seed)?);
        journal
            .commit(0, &events)
            .map_err(|e| format!("seed {}: {e}", seed.display()))?;
        journal.save_snapshot().map_err(|e| e.to_string())?;
    }

    let mut scheduler = Scheduler::new(&journal, options.checkpoint_every);
    // Reflections from model-driven agents are committed by this system, inside a tick.
    let reflections = sage_agents::reflection::Reflections::new();
    scheduler.add(reflections.clone());
    let mut reflected = 0usize;
    for plugin in plugins {
        if let Some(handler) = plugin.command_handler() {
            scheduler
                .commands_mut()
                .register(handler)
                .map_err(|e| format!("plugin `{}`: {e}", sage_core::System::name(&plugin)))?;
        }
        scheduler.add(plugin);
    }

    let stop = Arc::new(AtomicBool::new(false));
    {
        let stop = Arc::clone(&stop);
        ctrlc::set_handler(move || stop.store(true, Ordering::SeqCst))
            .map_err(|e| format!("cannot install shutdown handler: {e}"))?;
    }

    // Memory is rebuilt from the log, so a restarted world's agents remember exactly what an
    // uninterrupted world's would. Agents then think for the first tick this run will step.
    let mut agents = Agents::rebuild(journal.log(), &Upcasters::core())?
        .with_verbs(scheduler.commands_mut().verbs())
        .with_lexicon(lexicon.clone());
    if let (Some(url), Some(model)) = (&options.llm_url, &options.llm_model) {
        let config = LlmConfig {
            url: url.clone(),
            model: model.clone(),
            api_key: std::env::var("SAGE_LLM_API_KEY")
                .ok()
                .filter(|k| !k.is_empty()),
            // Never give up on a request before its answer would be dropped anyway.
            timeout: Duration::from_secs(options.llm_max_wait.max(60)),
            workers: options.llm_workers,
        };
        // The answer limit is set in seconds, because that is how long a model takes; the
        // agents count ticks. When running as fast as possible there is no clock to go by.
        let max_answer_age = match options.hz {
            0 => sage_agents::llm::MAX_ANSWER_AGE,
            hz => options.llm_max_wait.saturating_mul(u64::from(hz)),
        };
        agents = agents.with_max_answer_age(max_answer_age);
        println!(
            "llm url={url} model={model} workers={} max_wait={}s ({max_answer_age} ticks)",
            options.llm_workers, options.llm_max_wait
        );
        warm_up(config.clone());
        let relevance = match (&options.embed_url, &options.embed_model) {
            (Some(embed_url), Some(embed_model)) => {
                let cache_path = {
                    let mut name = options.world.as_os_str().to_owned();
                    name.push(".embeddings.db");
                    std::path::PathBuf::from(name)
                };
                let key = std::env::var("SAGE_EMBED_API_KEY")
                    .or_else(|_| std::env::var("SAGE_LLM_API_KEY"))
                    .ok()
                    .filter(|k| !k.is_empty());
                println!(
                    "embeddings url={embed_url} model={embed_model} cache={}",
                    cache_path.display()
                );
                Relevance::embedded(
                    HttpEmbedder::new(
                        embed_url.clone(),
                        embed_model.clone(),
                        key,
                        Duration::from_secs(60),
                    ),
                    EmbeddingCache::open(&cache_path)?,
                )
            }
            _ => Relevance::Lexical,
        };
        agents = agents.with_thinker(Thinker::start_with(
            HttpTransport::new(config),
            relevance,
            options.llm_workers,
        ));
    }
    let mut agent_commands = 0usize;
    let mut model_failures = 0usize;
    for thought in agents.think(journal.world(), scheduler.tick() + 1) {
        scheduler.submit(thought.agent, thought.command);
        agent_commands += 1;
    }
    let agent_count = journal
        .world()
        .entities_with(<sage_agents::Mind as sage_core::Component>::NAME)
        .len();
    println!(
        "start world={} tick={} seq={} entities={} agents={agent_count}",
        options.world.display(),
        scheduler.tick(),
        journal.world().last_seq(),
        journal.world().len()
    );

    let mut players = match &options.listen {
        None => None,
        Some(listen) => {
            let accounts_path = {
                let mut name = options.world.as_os_str().to_owned();
                name.push(".accounts.db");
                std::path::PathBuf::from(name)
            };
            let (to_engine, inbound) = std::sync::mpsc::channel();
            let addr = crate::net::start(listen, accounts_path.clone(), to_engine)?;
            println!(
                "listening ws://{addr}/ws accounts={} play=http://{addr}/ client={}",
                accounts_path.display(),
                if crate::web::client_built() {
                    "embedded"
                } else {
                    "not-built"
                }
            );
            Some(crate::players::Players::new(
                inbound,
                crate::accounts::Accounts::open(&accounts_path)?,
                options.start_place.map(sage_core::EntityId),
                lexicon,
            ))
        }
    };

    let period = (options.hz > 0).then(|| Duration::from_secs(1) / options.hz);
    let mut deadline = Instant::now();
    let mut refused_total = 0usize;
    while !stop.load(Ordering::SeqCst)
        && options
            .until_tick
            .is_none_or(|until| scheduler.tick() < until)
    {
        if let Some(players) = &mut players {
            players.before_step(&mut journal, &mut scheduler)?;
        }
        let report = scheduler.step(&mut journal).map_err(|e| e.to_string())?;
        if let Some(players) = &mut players {
            players.after_step(journal.world(), &report);
        }
        for refused in &report.refused {
            eprintln!(
                "tick={} refused system={} index={}: {}",
                report.tick, refused.system, refused.index, refused.error
            );
        }
        refused_total += report.refused.len();
        agents.observe(&report);
        for thought in agents.think(journal.world(), report.tick + 1) {
            scheduler.submit(thought.agent, thought.command);
            agent_commands += 1;
        }
        let collected = agents.collect(journal.world(), report.tick + 1);
        for thought in collected.thoughts {
            scheduler.submit(thought.agent, thought.command);
            agent_commands += 1;
        }
        for (agent, why) in collected.failed {
            eprintln!("tick={} model agent={}: {why}", report.tick, agent.0);
            model_failures += 1;
        }
        for (agent, text) in collected.reflections {
            reflections.push(agent, text);
            reflected += 1;
        }
        for (agent, warning) in collected.warnings {
            eprintln!("tick={} model agent={}: {warning}", report.tick, agent.0);
        }
        for suspended in &report.suspended {
            eprintln!(
                "tick={} suspended system={}: {}",
                report.tick, suspended.system, suspended.reason
            );
        }

        if report.tick.is_multiple_of(options.snapshot_every) {
            journal.save_snapshot().map_err(|e| e.to_string())?;
        }
        if report.tick.is_multiple_of(options.report_every) {
            let signed_in = players.as_ref().map_or(0, |p| p.signed_in());
            println!(
                "tick={} seq={} entities={} refused={} agent_commands={agent_commands} model_failures={model_failures} reflections={reflected} players={signed_in}",
                report.tick,
                journal.world().last_seq(),
                journal.world().len(),
                refused_total
            );
        }

        if let Some(period) = period {
            deadline += period;
            let now = Instant::now();
            if deadline > now {
                std::thread::sleep(deadline - now);
            } else if now - deadline > period * 10 {
                // Far behind: resync instead of running a burst of catch-up ticks.
                deadline = now;
            }
        }
    }

    scheduler
        .record_clock(&mut journal)
        .map_err(|e| e.to_string())?;
    journal.save_snapshot().map_err(|e| e.to_string())?;
    println!(
        "stop tick={} seq={} entities={} refused={} agent_commands={agent_commands} model_failures={model_failures} reflections={reflected}",
        scheduler.tick(),
        journal.world().last_seq(),
        journal.world().len(),
        refused_total
    );
    Ok(())
}

/// Loads a plugin only if `sage check` passes on its fragment directory, granting exactly the
/// capabilities its manifest declares.
fn load_checked_plugin(host: &PluginHost, dir: &Path) -> Result<PluginSystem, String> {
    let report = crate::check::check(dir);
    if !report.ok {
        return Err(format!(
            "plugin {} refused; sage check reports: {}",
            dir.display(),
            serde_json::to_string(&report).expect("reports serialize")
        ));
    }
    let text = std::fs::read_to_string(dir.join("fragment.yaml")).map_err(|e| e.to_string())?;
    let manifest = sage_schema::validate_manifest(&text)
        .manifest
        .expect("sage check passed, so the manifest is valid");
    let grants: Vec<&str> = manifest
        .capabilities
        .iter()
        .flatten()
        .map(String::as_str)
        .collect();
    let wasm = std::fs::read(dir.join("plugin.wasm")).map_err(|e| e.to_string())?;
    let plugin = host
        .load(&wasm, &grants, Limits::default())
        .map_err(|e| format!("plugin {}: {e}", dir.display()))?;
    println!(
        "plugin id={} version={} grants={}",
        manifest.id.as_str(),
        manifest.version,
        if grants.is_empty() {
            "none".to_owned()
        } else {
            grants.join(",")
        }
    );
    Ok(plugin)
}

pub fn inspect(path: &Path) -> Result<(), String> {
    if !path.exists() {
        return Err(format!("{}: no such file", path.display()));
    }
    let from_snapshot = open(path)?;
    let snapshot_seq = sage_core::EventLog::latest_snapshot(from_snapshot.log())
        .map_err(|e| e.to_string())?
        .map(|s| s.seq);
    let log = SqliteLog::open(path).map_err(|e| e.to_string())?;
    let from_genesis = Journal::open_from_genesis(log, sage_agents::registry(), Upcasters::core())
        .map_err(|e| e.to_string())?;
    let agree =
        from_snapshot.world().snapshot().to_bytes() == from_genesis.world().snapshot().to_bytes();
    let world = from_genesis.world();
    println!(
        "{}",
        serde_json::json!({
            "tick": world.tick(),
            "last_seq": world.last_seq(),
            "entities": world.len(),
            "snapshot_seq": snapshot_seq,
            "snapshot_matches_replay": agree,
        })
    );
    if agree {
        Ok(())
    } else {
        Err("snapshot and full replay disagree".into())
    }
}
