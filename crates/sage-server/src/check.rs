//! `sage check <fragment-dir>`: can this engine use this fragment?
//!
//! Checks run in order and a failed check skips the ones that depend on it:
//! 1. `manifest`: `fragment.yaml` passes `sage_schema` validation.
//! 2. `engine`: the manifest's engine requirement accepts this engine's version.
//! 3. `capabilities` (plugins): `plugin.wasm` imports exactly the declared capabilities, and
//!    this engine serves each of them.
//! 4. `boot` (plugins): the plugin loads under its declared grants, reports its manifest id
//!    as its name, handles exactly the verbs in `provides.commands` without claiming a core
//!    verb, and survives one tick on an empty world within the default limits.
//!
//! The report is one line of JSON with a stable shape, for the Foundry and for scripts.

use std::path::Path;

use sage_core::{ComponentRegistry, Journal, Scheduler, Upcasters};
use sage_host::{GRANTABLE, Limits, PluginHost};
use sage_schema::{Kind, Manifest};
use sage_store::SqliteLog;
use serde::Serialize;

pub const ENGINE_VERSION: &str = env!("CARGO_PKG_VERSION");

#[derive(Serialize)]
pub struct Report {
    fragment: Option<String>,
    engine: &'static str,
    pub ok: bool,
    checks: Vec<Check>,
}

#[derive(Serialize)]
struct Check {
    check: &'static str,
    status: Status,
    problems: Vec<String>,
}

#[derive(Serialize, Clone, Copy, PartialEq)]
#[serde(rename_all = "lowercase")]
enum Status {
    Pass,
    Fail,
    Skipped,
}

impl Report {
    fn push(&mut self, check: &'static str, problems: Vec<String>) -> bool {
        let status = if problems.is_empty() {
            Status::Pass
        } else {
            Status::Fail
        };
        self.checks.push(Check {
            check,
            status,
            problems,
        });
        status == Status::Pass
    }

    fn skip(&mut self, checks: &[&'static str]) {
        for check in checks {
            self.checks.push(Check {
                check,
                status: Status::Skipped,
                problems: Vec::new(),
            });
        }
    }
}

pub fn check(dir: &Path) -> Report {
    let mut report = Report {
        fragment: None,
        engine: ENGINE_VERSION,
        ok: false,
        checks: Vec::new(),
    };
    let later = ["engine", "capabilities", "boot"];

    let manifest_path = dir.join("fragment.yaml");
    let manifest = match std::fs::read_to_string(&manifest_path) {
        Err(e) => {
            report.push(
                "manifest",
                vec![format!("{}: {e}", manifest_path.display())],
            );
            report.skip(&later);
            return report;
        }
        Ok(text) => {
            let validation = sage_schema::validate_manifest(&text);
            let problems = validation
                .problems
                .iter()
                .map(|p| {
                    if p.path.is_empty() {
                        p.message.clone()
                    } else {
                        format!("{}: {}", p.path, p.message)
                    }
                })
                .collect();
            if !report.push("manifest", problems) {
                report.skip(&later);
                return report;
            }
            validation
                .manifest
                .expect("valid report carries the manifest")
        }
    };
    report.fragment = Some(manifest.id.as_str().to_owned());

    let engine: semver::Version = ENGINE_VERSION.parse().expect("crate version is semver");
    let engine_ok = report.push(
        "engine",
        if manifest.engine_requirement().matches(&engine) {
            Vec::new()
        } else {
            vec![format!(
                "requires engine `{}`; this engine is {ENGINE_VERSION}",
                manifest.engine
            )]
        },
    );

    if manifest.kind != Kind::Plugin {
        report.skip(&["capabilities", "boot"]);
        report.ok = engine_ok;
        return report;
    }

    let plugin_ok = check_plugin(&mut report, dir, &manifest);
    report.ok = engine_ok && plugin_ok;
    report
}

fn check_plugin(report: &mut Report, dir: &Path, manifest: &Manifest) -> bool {
    let wasm_path = dir.join("plugin.wasm");
    let wasm = match std::fs::read(&wasm_path) {
        Ok(wasm) => wasm,
        Err(e) => {
            report.push(
                "capabilities",
                vec![format!("{}: {e}", wasm_path.display())],
            );
            report.skip(&["boot"]);
            return false;
        }
    };
    let host = match PluginHost::new() {
        Ok(host) => host,
        Err(e) => {
            report.push("capabilities", vec![e.to_string()]);
            report.skip(&["boot"]);
            return false;
        }
    };

    let declared: Vec<&str> = manifest
        .capabilities
        .as_deref()
        .unwrap_or_default()
        .iter()
        .map(String::as_str)
        .collect();
    let mut problems = Vec::new();
    for capability in &declared {
        if !GRANTABLE.contains(capability) {
            problems.push(format!(
                "declares `{capability}`, which this engine does not serve (it serves {})",
                GRANTABLE.join(", ")
            ));
        }
    }
    match host.imports(&wasm) {
        Err(e) => problems.push(e.to_string()),
        Ok(imports) => {
            for import in &imports {
                if !declared.contains(&import.as_str()) {
                    problems.push(format!(
                        "imports `{import}` but does not declare it in capabilities"
                    ));
                }
            }
            for capability in &declared {
                if !imports.iter().any(|i| i == capability) {
                    problems.push(format!(
                        "declares `{capability}` but never imports it; remove it so players \
                         are not asked to grant it"
                    ));
                }
            }
        }
    }
    if !report.push("capabilities", problems) {
        report.skip(&["boot"]);
        return false;
    }

    let mut problems = Vec::new();
    match host.load(&wasm, &declared, Limits::default()) {
        Err(e) => problems.push(e.to_string()),
        Ok(plugin) => {
            use sage_core::System;
            if plugin.name() != manifest.id.as_str() {
                problems.push(format!(
                    "plugin names itself `{}` but the manifest id is `{}`",
                    plugin.name(),
                    manifest.id.as_str()
                ));
            }
            let handled: std::collections::BTreeSet<&str> =
                plugin.verbs().iter().map(String::as_str).collect();
            let provided: std::collections::BTreeSet<&str> = manifest
                .provides
                .commands
                .iter()
                .map(String::as_str)
                .collect();
            for verb in handled.difference(&provided) {
                problems.push(format!(
                    "handles `{verb}` but provides.commands does not list it"
                ));
            }
            for verb in provided.difference(&handled) {
                problems.push(format!(
                    "provides.commands lists `{verb}` but the plugin does not handle it"
                ));
            }
            if let Some(handler) = plugin.command_handler()
                && let Err(conflict) = sage_core::Commands::with_core().register(handler)
            {
                problems.push(conflict);
            }
            match dry_run(plugin) {
                Ok(()) => {}
                Err(reason) => problems.push(reason),
            }
        }
    }
    report.push("boot", problems)
}

/// One tick on an empty, in-memory world.
fn dry_run(plugin: sage_host::PluginSystem) -> Result<(), String> {
    let log = SqliteLog::open_in_memory().map_err(|e| e.to_string())?;
    let mut journal = Journal::open(log, ComponentRegistry::with_core(), Upcasters::new())
        .map_err(|e| e.to_string())?;
    let mut scheduler = Scheduler::new(&journal, u64::MAX);
    scheduler.add(plugin);
    let step = scheduler.step(&mut journal).map_err(|e| e.to_string())?;
    match step.suspended.first() {
        Some(suspended) => Err(format!(
            "suspended on its first tick on an empty world: {}",
            suspended.reason
        )),
        None => Ok(()),
    }
}

pub fn run(dir: &Path) -> Result<(), String> {
    let report = check(dir);
    println!(
        "{}",
        serde_json::to_string(&report).expect("reports serialize")
    );
    if report.ok {
        Ok(())
    } else {
        Err(format!("{} failed its checks", dir.display()))
    }
}
