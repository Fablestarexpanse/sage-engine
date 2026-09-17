//! `sage card <file>`: read a Tavern character card (PNG or JSON) and show the agent it becomes.
//!
//! The report is one line of JSON with a stable shape: whether the card is usable, where in the
//! file it was found, its specification by shape, every finding from reading and converting it,
//! and the agent. Nothing is written anywhere; placing the agent in a world is a separate step.

use std::io::Read;
use std::path::Path;

use sage_agents::card::{ImportedAgent, agent_from_card};
use sage_schema::card::{self, Finding, MAX_PNG_BYTES, Severity, Spec};
use sage_schema::png::SIGNATURE;
use serde::Serialize;

#[derive(Serialize)]
pub struct Report {
    pub ok: bool,
    source: Option<String>,
    spec: Option<Spec>,
    findings: Vec<Finding>,
    agent: Option<ImportedAgent>,
}

/// Reads `bytes` as a PNG when they start like one or the file is named `.png`, else as JSON.
pub fn report(bytes: &[u8], named_png: bool) -> Report {
    let read = if named_png || bytes.starts_with(&SIGNATURE) {
        card::read_png(bytes)
    } else {
        card::read_json(bytes)
    };
    let mut findings = read.findings;
    let agent = read.card.as_ref().filter(|_| read.ok).map(|card| {
        let (agent, converted) = agent_from_card(card);
        findings.extend(converted);
        agent
    });
    findings.sort_by_key(|f| f.severity);
    let ok = agent.is_some() && findings.iter().all(|f| f.severity != Severity::Error);
    Report {
        ok,
        source: read.source,
        spec: read.spec,
        findings,
        agent,
    }
}

pub fn run(path: &Path) -> Result<(), String> {
    let file = std::fs::File::open(path).map_err(|e| format!("{}: {e}", path.display()))?;
    let mut bytes = Vec::new();
    // Read one byte past the limit so an oversized file is reported, not silently cut.
    file.take(MAX_PNG_BYTES as u64 + 1)
        .read_to_end(&mut bytes)
        .map_err(|e| format!("{}: {e}", path.display()))?;
    let named_png = path
        .extension()
        .is_some_and(|e| e.eq_ignore_ascii_case("png"));
    let report = report(&bytes, named_png);
    println!(
        "{}",
        serde_json::to_string(&report).expect("reports serialize")
    );
    if report.ok {
        Ok(())
    } else {
        Err(format!("{} is not a usable character card", path.display()))
    }
}
