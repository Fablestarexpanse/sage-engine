//! `sage place <world.db> <id>[@version]`: put an installed agent fragment into a world.
//!
//! Placing is ordinary events in one transaction at the world's current tick: the entity, its
//! name, `sage.actor`, `sage.located`, `sage.mind`, `sage.origin` naming the fragment, and one
//! `sage.mind.remembered` occurrence per seed memory. The world must not be running (the log
//! has one writer), and the fragment is verified against its digest again before use.

use std::path::Path;

use sage_core::{Actor, Component, Describable, EntityId, Origin, Place};
use serde::Serialize;

use crate::library::Installed;

#[derive(Serialize)]
struct Report {
    ok: bool,
    fragment: String,
    version: String,
    entity: u64,
    name: String,
    place: u64,
    memories: usize,
    tick: u64,
}

/// Placement choices.
#[derive(Debug, Default, PartialEq)]
pub struct PlaceOptions {
    /// Place entity id; default the lowest-numbered place.
    pub at: Option<u64>,
    /// Name instead of the card's, e.g. for a second copy.
    pub name: Option<String>,
}

pub fn run(world: &Path, spec: &str, options: &PlaceOptions) -> Result<(), String> {
    let (id, version) = match spec.split_once('@') {
        Some((id, version)) => (id, Some(version)),
        None => (spec, None),
    };
    let installed = Installed::find(world, id, version)?;
    let mut agent = installed.agent()?;
    if let Some(name) = &options.name {
        let name = name.split_whitespace().collect::<Vec<_>>().join(" ");
        if name.is_empty() || name.chars().count() > 64 {
            return Err("--name must be 1 to 64 characters".into());
        }
        agent.name = name;
    }

    if !world.exists() {
        return Err(format!("{}: no such world", world.display()));
    }
    let (mut journal, _lock) = crate::run::open_for_writing(world)?;
    let state = journal.world();
    let place = match options.at {
        Some(at) => {
            let at = EntityId(at);
            if state.get::<Place>(at).is_none() {
                return Err(format!("entity {} is not a place", at.0));
            }
            at
        }
        None => state
            .entities_with(Place::NAME)
            .into_iter()
            .next()
            .ok_or("this world has no place to put an agent in")?,
    };
    let taken = state.entities_with(Actor::NAME).into_iter().any(|actor| {
        state
            .get::<Describable>(actor)
            .is_some_and(|d| d.name.to_lowercase() == agent.name.to_lowercase())
    });
    if taken {
        return Err(format!(
            "an actor named `{}` is already in this world; choose another with --name",
            agent.name
        ));
    }

    let entity = state.next_entity_id();
    let tick = state.tick();
    let origin = Origin {
        fragment: installed.manifest.id.as_str().to_owned(),
        version: installed.manifest.version.clone(),
        digest: installed.digest.clone(),
    };
    journal
        .commit(tick, &agent.placement(entity, place, &origin))
        .map_err(|e| e.to_string())?;
    let report = Report {
        ok: true,
        fragment: origin.fragment,
        version: origin.version,
        entity: entity.0,
        name: agent.name,
        place: place.0,
        memories: agent.seed_memories.len(),
        tick,
    };
    println!(
        "{}",
        serde_json::to_string(&report).expect("reports serialize")
    );
    Ok(())
}
