//! Wasmtime host for code fragments.
//!
//! A plugin is a WebAssembly component built against the `sage:core` WIT package. It runs as
//! a [`sage_core::System`]: it reads the world through granted interfaces and proposes events,
//! which the world validates like any other events. It cannot change the world directly.
//!
//! **The seal.** A plugin may import only interfaces it was granted. Loading refuses a plugin
//! that imports anything else and names the interface, before any plugin code runs.
//!
//! **Limits.** Each run gets a fuel budget (deterministic, unlike wall-clock interruption) and
//! the store has a memory cap. A plugin that runs out of either, traps, or returns an error is
//! suspended by the scheduler; the world keeps running.

use std::sync::Arc;

use sage_core::{EntityId, Event, EventRecord, System, Upcasters, World};
use thiserror::Error;
use wasmtime::component::{Component, HasSelf, Linker};
use wasmtime::{Config, Engine, Store, StoreLimits, StoreLimitsBuilder, Trap};

mod bindings {
    wasmtime::component::bindgen!({
        path: "../../wit/core",
        world: "plugin",
        imports: { default: trappable },
    });
}

use bindings::Plugin;
use bindings::sage::core::{entities, space, types};

/// Version of the `sage:core` WIT package this host serves.
pub const WIT_VERSION: &str = "0.1.0";

/// Interfaces a plugin can be granted, by full name.
pub const GRANTABLE: [&str; 2] = ["sage:core/entities@0.1.0", "sage:core/space@0.1.0"];

/// Type-only interfaces every plugin may import; they carry no functions.
const ALWAYS_ALLOWED: [&str; 1] = ["sage:core/types@0.1.0"];

/// Resource limits for one plugin.
#[derive(Clone, Copy, Debug)]
pub struct Limits {
    /// Fuel for each call into the plugin. Roughly one unit per WebAssembly instruction.
    pub fuel_per_call: u64,
    /// Maximum linear memory, in bytes.
    pub memory_bytes: usize,
}

impl Default for Limits {
    fn default() -> Self {
        Limits {
            fuel_per_call: 10_000_000,
            memory_bytes: 16 * 1024 * 1024,
        }
    }
}

/// Why a plugin could not be loaded.
#[derive(Debug, Error)]
pub enum LoadError {
    /// The bytes are not a valid component.
    #[error("not a valid plugin component: {0}")]
    Invalid(String),
    /// A grant names an interface this host does not serve.
    #[error("cannot grant unknown interface `{0}` (this host serves {GRANTABLE:?})")]
    UnknownGrant(String),
    /// The plugin imports an interface it was not granted.
    #[error("plugin imports `{interface}`, which it was not granted")]
    Ungranted {
        /// The ungranted import.
        interface: String,
    },
    /// Instantiation or the `name` call failed.
    #[error("plugin failed to start: {0}")]
    Start(String),
}

/// Compiles and loads plugins. One host can load many plugins.
pub struct PluginHost {
    engine: Engine,
}

struct HostState {
    world: Option<Arc<World>>,
    limits: StoreLimits,
}

impl HostState {
    fn world(&self) -> wasmtime::Result<&World> {
        self.world
            .as_deref()
            .ok_or_else(|| wasmtime::format_err!("world accessed outside a system run"))
    }
}

impl PluginHost {
    /// A host with fuel metering on.
    pub fn new() -> Result<Self, LoadError> {
        let mut config = Config::new();
        config.consume_fuel(true);
        let engine = Engine::new(&config).map_err(|e| LoadError::Start(e.to_string()))?;
        Ok(PluginHost { engine })
    }

    /// Loads a plugin component with `grants` (full interface names from [`GRANTABLE`]).
    /// Refuses the plugin if it imports anything not granted.
    pub fn load(
        &self,
        wasm: &[u8],
        grants: &[&str],
        limits: Limits,
    ) -> Result<PluginSystem, LoadError> {
        if let Some(unknown) = grants.iter().find(|g| !GRANTABLE.contains(g)) {
            return Err(LoadError::UnknownGrant((*unknown).to_owned()));
        }
        let component =
            Component::new(&self.engine, wasm).map_err(|e| LoadError::Invalid(format!("{e:#}")))?;

        for (name, _) in component.component_type().imports(&self.engine) {
            if !grants.contains(&name) && !ALWAYS_ALLOWED.contains(&name) {
                return Err(LoadError::Ungranted {
                    interface: name.to_owned(),
                });
            }
        }

        // The linker only ever holds granted interfaces, so the seal holds even if the check
        // above were wrong: instantiation would fail on the missing import.
        let mut linker = Linker::<HostState>::new(&self.engine);
        let start = |e: wasmtime::Error| LoadError::Start(format!("{e:#}"));
        types::add_to_linker::<_, HasSelf<_>>(&mut linker, |s| s).map_err(start)?;
        if grants.contains(&GRANTABLE[0]) {
            entities::add_to_linker::<_, HasSelf<_>>(&mut linker, |s| s).map_err(start)?;
        }
        if grants.contains(&GRANTABLE[1]) {
            space::add_to_linker::<_, HasSelf<_>>(&mut linker, |s| s).map_err(start)?;
        }

        let state = HostState {
            world: None,
            limits: StoreLimitsBuilder::new()
                .memory_size(limits.memory_bytes)
                .trap_on_grow_failure(true)
                .build(),
        };
        let mut store = Store::new(&self.engine, state);
        store.limiter(|state| &mut state.limits);
        store.set_fuel(limits.fuel_per_call).map_err(start)?;
        let plugin = Plugin::instantiate(&mut store, &component, &linker).map_err(start)?;
        store.set_fuel(limits.fuel_per_call).map_err(start)?;
        let name = plugin
            .sage_core_system()
            .call_name(&mut store)
            .map_err(start)?;

        Ok(PluginSystem {
            // Plugins are loaded a handful of times per process, so leaking the name to get
            // the `&'static str` the scheduler reports with costs nothing that matters.
            name: Box::leak(name.into_boxed_str()),
            store,
            plugin,
            limits,
            upcasters: Upcasters::new(),
            last_fuel_used: 0,
        })
    }
}

/// A loaded plugin, ready to add to a [`sage_core::Scheduler`].
pub struct PluginSystem {
    name: &'static str,
    store: Store<HostState>,
    plugin: Plugin,
    limits: Limits,
    upcasters: Upcasters,
    last_fuel_used: u64,
}

impl PluginSystem {
    /// Fuel the most recent run used.
    pub fn last_fuel_used(&self) -> u64 {
        self.last_fuel_used
    }
}

impl System for PluginSystem {
    fn name(&self) -> &'static str {
        self.name
    }

    fn run(&mut self, world: &Arc<World>, tick: u64) -> Result<Vec<Event>, String> {
        self.store
            .set_fuel(self.limits.fuel_per_call)
            .map_err(|e| e.to_string())?;
        self.store.data_mut().world = Some(Arc::clone(world));
        let result = self
            .plugin
            .sage_core_system()
            .call_run(&mut self.store, tick);
        // Release the world before anything else, including on a trap, so the journal can
        // commit.
        self.store.data_mut().world = None;
        self.last_fuel_used = self.limits.fuel_per_call - self.store.get_fuel().unwrap_or(0);

        let records = match result {
            Ok(Ok(records)) => records,
            Ok(Err(message)) => return Err(format!("plugin returned an error: {message}")),
            Err(error) => {
                return Err(match error.downcast_ref::<Trap>() {
                    Some(Trap::OutOfFuel) => format!(
                        "out of fuel (budget {} per call)",
                        self.limits.fuel_per_call
                    ),
                    _ if format!("{error:#}").contains("forcing trap when growing memory") => {
                        format!("memory cap exceeded ({} bytes)", self.limits.memory_bytes)
                    }
                    _ => format!("trapped: {error:#}"),
                });
            }
        };

        records
            .into_iter()
            .enumerate()
            .map(|(index, record)| {
                let payload = serde_json::from_str(&record.payload).map_err(|e| {
                    format!(
                        "event {index} (`{}`) payload is not JSON: {e}",
                        record.event_type
                    )
                })?;
                let record = EventRecord {
                    event_type: record.event_type,
                    schema_version: record.schema_version,
                    payload,
                };
                Event::from_record(&record, &self.upcasters)
                    .map_err(|e| format!("event {index} is not a valid event: {e}"))
            })
            .collect()
    }
}

impl types::Host for HostState {}

impl entities::Host for HostState {
    fn next_entity_id(&mut self) -> wasmtime::Result<u64> {
        Ok(self.world()?.next_entity_id().0)
    }

    fn get_component(&mut self, id: u64, component: String) -> wasmtime::Result<Option<String>> {
        Ok(self
            .world()?
            .component_json(EntityId(id), &component)
            .map(|value| value.to_string()))
    }

    fn entities_with(&mut self, component: String) -> wasmtime::Result<Vec<u64>> {
        Ok(self
            .world()?
            .entities_with(&component)
            .into_iter()
            .map(|id| id.0)
            .collect())
    }
}

impl space::Host for HostState {
    fn links_from(&mut self, place: u64) -> wasmtime::Result<Vec<space::Link>> {
        Ok(self
            .world()?
            .links_from(EntityId(place))
            .into_iter()
            .map(|(id, link)| space::Link {
                id: id.0,
                from: link.from.0,
                to: link.to.0,
                label: link.label,
            })
            .collect())
    }

    fn contents(&mut self, container: u64) -> wasmtime::Result<Vec<u64>> {
        Ok(self
            .world()?
            .contents(EntityId(container))
            .into_iter()
            .map(|id| id.0)
            .collect())
    }
}
