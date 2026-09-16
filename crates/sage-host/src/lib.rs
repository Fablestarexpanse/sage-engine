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

use std::cell::RefCell;
use std::rc::Rc;
use std::sync::Arc;

use sage_core::{
    CommandHandler, CommandOutcome, EntityId, Event, EventRecord, Line, System, Upcasters, World,
};
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

/// Bindings for the commands export, reusing the plugin world's import bindings.
mod command_bindings {
    wasmtime::component::bindgen!({
        path: "../../wit/core",
        world: "command-plugin",
        imports: { default: trappable },
        with: {
            "sage:core/types": crate::bindings::sage::core::types,
            "sage:core/entities": crate::bindings::sage::core::entities,
            "sage:core/space": crate::bindings::sage::core::space,
        },
    });
}

use bindings::Plugin;
use bindings::sage::core::{entities, space, types};
use command_bindings::CommandPlugin;

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
    /// Instantiation or a startup call failed.
    #[error("plugin failed to start: {0}")]
    Start(String),
    /// The plugin broke the host's rules for names, verbs or lexicon keys.
    #[error("plugin breaks the plugin contract: {0}")]
    Contract(String),
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

    /// The interfaces a plugin component imports that need a grant, sorted. Type-only
    /// interfaces every plugin may use are left out.
    pub fn imports(&self, wasm: &[u8]) -> Result<Vec<String>, LoadError> {
        Ok(self.imports_of(&self.compile(wasm)?))
    }

    fn compile(&self, wasm: &[u8]) -> Result<Component, LoadError> {
        Component::new(&self.engine, wasm).map_err(|e| LoadError::Invalid(format!("{e:#}")))
    }

    fn imports_of(&self, component: &Component) -> Vec<String> {
        let mut names: Vec<String> = component
            .component_type()
            .imports(&self.engine)
            .map(|(name, _)| name.to_owned())
            .filter(|name| !ALWAYS_ALLOWED.contains(&name.as_str()))
            .collect();
        names.sort();
        names
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
        let component = self.compile(wasm)?;
        if let Some(interface) = self
            .imports_of(&component)
            .into_iter()
            .find(|name| !grants.contains(&name.as_str()))
        {
            return Err(LoadError::Ungranted { interface });
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
        let instance = linker.instantiate(&mut store, &component).map_err(start)?;
        let plugin = Plugin::new(&mut store, &instance).map_err(start)?;
        let exports_commands = component
            .component_type()
            .exports(&self.engine)
            .any(|(name, _)| name == COMMANDS_EXPORT);
        let commands = if exports_commands {
            Some(CommandPlugin::new(&mut store, &instance).map_err(start)?)
        } else {
            None
        };

        let mut instance = Instance {
            name: "",
            store,
            plugin,
            commands,
            limits,
            upcasters: Upcasters::core(),
            last_fuel_used: 0,
            poisoned: None,
        };
        let name = instance
            .call(None, |plugin, _, store| {
                plugin.sage_core_system().call_name(store)
            })
            .map_err(LoadError::Start)?;
        // Plugins are loaded a handful of times per process, so leaking the name to get the
        // `&'static str` the scheduler reports with costs nothing that matters.
        let name: &'static str = Box::leak(name.into_boxed_str());
        instance.name = name;

        let (verbs, lexicon) = if instance.commands.is_some() {
            let verbs = instance
                .call(None, |_, commands, store| {
                    commands
                        .expect("checked")
                        .sage_core_commands()
                        .call_verbs(store)
                })
                .map_err(LoadError::Start)?;
            let lexicon = instance
                .call(None, |_, commands, store| {
                    commands
                        .expect("checked")
                        .sage_core_commands()
                        .call_lexicon(store)
                })
                .map_err(LoadError::Start)?;
            (verbs, lexicon)
        } else {
            (Vec::new(), Vec::new())
        };
        let prefix = format!("{name}.");
        if let Some((key, _)) = lexicon.iter().find(|(key, _)| !key.starts_with(&prefix)) {
            return Err(LoadError::Contract(format!(
                "lexicon key `{key}` does not start with `{prefix}`"
            )));
        }

        Ok(PluginSystem {
            instance: Rc::new(RefCell::new(instance)),
            name,
            verbs,
            lexicon,
        })
    }
}

/// The WIT interface a command plugin exports.
pub const COMMANDS_EXPORT: &str = "sage:core/commands@0.1.0";

/// One plugin instance, shared by its system and its command handler.
struct Instance {
    name: &'static str,
    store: Store<HostState>,
    plugin: Plugin,
    commands: Option<CommandPlugin>,
    limits: Limits,
    upcasters: Upcasters,
    last_fuel_used: u64,
    /// Set after a trap. A trapped instance is never called again.
    poisoned: Option<String>,
}

impl Instance {
    /// Calls into the plugin with fresh fuel and the world lent for the call.
    fn call<T>(
        &mut self,
        world: Option<&Arc<World>>,
        call: impl FnOnce(&Plugin, Option<&CommandPlugin>, &mut Store<HostState>) -> wasmtime::Result<T>,
    ) -> Result<T, String> {
        if let Some(reason) = &self.poisoned {
            return Err(format!("plugin already failed: {reason}"));
        }
        self.store
            .set_fuel(self.limits.fuel_per_call)
            .map_err(|e| e.to_string())?;
        self.store.data_mut().world = world.map(Arc::clone);
        let result = call(&self.plugin, self.commands.as_ref(), &mut self.store);
        // Release the world before anything else, including on a trap, so the journal can
        // commit.
        self.store.data_mut().world = None;
        self.last_fuel_used = self.limits.fuel_per_call - self.store.get_fuel().unwrap_or(0);
        result.map_err(|error| {
            let reason = match error.downcast_ref::<Trap>() {
                Some(Trap::OutOfFuel) => format!(
                    "out of fuel (budget {} per call)",
                    self.limits.fuel_per_call
                ),
                _ if format!("{error:#}").contains("forcing trap when growing memory") => {
                    format!("memory cap exceeded ({} bytes)", self.limits.memory_bytes)
                }
                _ => format!("trapped: {error:#}"),
            };
            self.poisoned = Some(reason.clone());
            reason
        })
    }

    /// Turns plugin event records into events. Occurrences must use the plugin's own kinds.
    fn decode(&self, records: Vec<types::EventRecord>) -> Result<Vec<Event>, String> {
        let prefix = format!("{}.", self.name);
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
                let event = Event::from_record(&record, &self.upcasters)
                    .map_err(|e| format!("event {index} is not a valid event: {e}"))?;
                if let Event::Occurred(occurred) = &event
                    && !occurred.kind.starts_with(&prefix)
                {
                    return Err(format!(
                        "event {index} is a `{}` occurrence; plugin `{}` may only emit kinds \
                         starting with `{prefix}`",
                        occurred.kind, self.name
                    ));
                }
                Ok(event)
            })
            .collect()
    }
}

/// A loaded plugin, ready to add to a [`sage_core::Scheduler`].
pub struct PluginSystem {
    instance: Rc<RefCell<Instance>>,
    name: &'static str,
    verbs: Vec<String>,
    lexicon: Vec<(String, String)>,
}

impl PluginSystem {
    /// Fuel the most recent call into the plugin used.
    pub fn last_fuel_used(&self) -> u64 {
        self.instance.borrow().last_fuel_used
    }

    /// The command handler, if the plugin exports `commands`. It shares this plugin's
    /// instance: a trap in either suspends both.
    pub fn command_handler(&self) -> Option<PluginCommands> {
        self.instance.borrow().commands.as_ref()?;
        Some(PluginCommands {
            instance: Rc::clone(&self.instance),
            name: self.name,
            verbs: self.verbs.clone(),
        })
    }

    /// Verbs the plugin handles; empty if it exports no commands.
    pub fn verbs(&self) -> &[String] {
        &self.verbs
    }

    /// The plugin's default lexicon templates, every key prefixed with its name.
    pub fn lexicon(&self) -> &[(String, String)] {
        &self.lexicon
    }
}

impl System for PluginSystem {
    fn name(&self) -> &'static str {
        self.name
    }

    fn run(&mut self, world: &Arc<World>, tick: u64) -> Result<Vec<Event>, String> {
        let mut instance = self.instance.borrow_mut();
        let result = instance.call(Some(world), |plugin, _, store| {
            plugin.sage_core_system().call_run(store, tick)
        })?;
        let records = result.map_err(|message| format!("plugin returned an error: {message}"))?;
        instance.decode(records)
    }
}

/// A plugin's command handler, ready to register with [`sage_core::Commands`].
pub struct PluginCommands {
    instance: Rc<RefCell<Instance>>,
    name: &'static str,
    verbs: Vec<String>,
}

impl CommandHandler for PluginCommands {
    fn name(&self) -> &'static str {
        self.name
    }

    fn verbs(&self) -> Vec<String> {
        self.verbs.clone()
    }

    fn handle(
        &mut self,
        world: &Arc<World>,
        actor: EntityId,
        verb: &str,
        args: &str,
        tick: u64,
    ) -> Result<CommandOutcome, String> {
        let mut instance = self.instance.borrow_mut();
        let result = instance.call(Some(world), |_, commands, store| {
            commands
                .expect("PluginCommands exists only for command plugins")
                .sage_core_commands()
                .call_handle(store, actor.0, verb, args, tick)
        })?;
        let outcome = result.map_err(|message| format!("plugin returned an error: {message}"))?;
        let prefix = format!("{}.", self.name);
        let mut output = Vec::with_capacity(outcome.output.len());
        for line in outcome.output {
            if !line.key.starts_with(&prefix) {
                return Err(format!(
                    "output key `{}` does not start with `{prefix}`",
                    line.key
                ));
            }
            output.push(Line {
                key: line.key,
                params: line.params.into_iter().collect(),
            });
        }
        Ok(CommandOutcome {
            events: instance.decode(outcome.events)?,
            output,
        })
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
