//! World time. Each step advances the clock one tick and runs every system in registration
//! order. Each system sees the world after the systems before it in the same tick. A system
//! that fails is suspended for the rest of the scheduler's life; the world keeps running.

use std::sync::Arc;

use crate::event::{ClockAdvanced, Event};
use crate::journal::{EventLog, Journal, JournalError};
use crate::world::{ApplyError, World};

/// Behaviour that runs once per tick. A system reads the world and proposes events; it never
/// changes the world directly.
pub trait System {
    /// Stable name, used in reports.
    fn name(&self) -> &'static str;

    /// Events this system wants committed at `tick`. The batch commits all or nothing. An
    /// error suspends the system: it is not run again by this scheduler. Any clone of `world`
    /// must be dropped before returning.
    fn run(&mut self, world: &Arc<World>, tick: u64) -> Result<Vec<Event>, String>;
}

/// A system's batch that the world refused. The world keeps running.
#[derive(Debug, PartialEq)]
pub struct SystemRefused {
    /// System name.
    pub system: &'static str,
    /// Position of the refused event in the batch.
    pub index: usize,
    /// Why.
    pub error: ApplyError,
}

/// A system that failed and will not run again.
#[derive(Debug, PartialEq)]
pub struct SystemSuspended {
    /// System name.
    pub system: &'static str,
    /// The system's error.
    pub reason: String,
}

/// What happened in one step.
#[derive(Debug, Default, PartialEq)]
pub struct StepReport {
    /// The tick that ran.
    pub tick: u64,
    /// Systems whose batches committed, in order.
    pub committed: Vec<&'static str>,
    /// Systems whose batches were refused.
    pub refused: Vec<SystemRefused>,
    /// Systems that failed this tick and are now suspended.
    pub suspended: Vec<SystemSuspended>,
    /// Whether an idle-clock checkpoint was recorded.
    pub checkpoint: bool,
}

/// Runs systems tick by tick.
pub struct Scheduler {
    systems: Vec<(Box<dyn System>, bool)>,
    tick: u64,
    checkpoint_every: u64,
}

impl Scheduler {
    /// Starts after the last tick in `journal`'s log. While nothing happens, a `ClockAdvanced`
    /// event is recorded every `checkpoint_every` ticks, so a crash loses at most that many
    /// ticks of world time. Panics if `checkpoint_every` is 0.
    pub fn new<L: EventLog>(journal: &Journal<L>, checkpoint_every: u64) -> Scheduler {
        assert!(checkpoint_every > 0, "checkpoint_every must be at least 1");
        Scheduler {
            systems: Vec::new(),
            tick: journal.world().tick(),
            checkpoint_every,
        }
    }

    /// Adds a system after the ones already added.
    pub fn add(&mut self, system: impl System + 'static) -> &mut Self {
        self.systems.push((Box::new(system), false));
        self
    }

    /// Names of systems that are suspended, in registration order.
    pub fn suspended(&self) -> Vec<&'static str> {
        self.systems
            .iter()
            .filter(|(_, suspended)| *suspended)
            .map(|(system, _)| system.name())
            .collect()
    }

    /// The last tick that ran.
    pub fn tick(&self) -> u64 {
        self.tick
    }

    /// Advances one tick and runs every system. Only a log failure is an error; a refused
    /// system batch is reported and the other systems still run.
    pub fn step<L: EventLog>(
        &mut self,
        journal: &mut Journal<L>,
    ) -> Result<StepReport, JournalError> {
        self.tick += 1;
        let tick = self.tick;
        let mut report = StepReport {
            tick,
            ..StepReport::default()
        };
        for (system, suspended) in &mut self.systems {
            if *suspended {
                continue;
            }
            let events = match system.run(journal.world_handle(), tick) {
                Ok(events) => events,
                Err(reason) => {
                    *suspended = true;
                    report.suspended.push(SystemSuspended {
                        system: system.name(),
                        reason,
                    });
                    continue;
                }
            };
            if events.is_empty() {
                continue;
            }
            match journal.commit(tick, &events) {
                Ok(_) => report.committed.push(system.name()),
                Err(JournalError::Refused { index, error }) => report.refused.push(SystemRefused {
                    system: system.name(),
                    index,
                    error,
                }),
                Err(other) => return Err(other),
            }
        }
        if journal.world().tick() + self.checkpoint_every <= tick {
            journal.commit(tick, &[Event::ClockAdvanced(ClockAdvanced {})])?;
            report.checkpoint = true;
        }
        Ok(report)
    }

    /// Records the scheduler's current tick in the log if the log is behind it, so a clean
    /// shutdown loses no world time. Returns whether anything was written.
    pub fn record_clock<L: EventLog>(
        &self,
        journal: &mut Journal<L>,
    ) -> Result<bool, JournalError> {
        if journal.world().tick() >= self.tick {
            return Ok(false);
        }
        journal.commit(self.tick, &[Event::ClockAdvanced(ClockAdvanced {})])?;
        Ok(true)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::journal::test_log::MemoryLog;
    use crate::{
        Component, ComponentRegistry, ComponentSet, Describable, EntityCreated, EntityId, Upcasters,
    };

    fn open(log: MemoryLog) -> Journal<MemoryLog> {
        Journal::open(log, ComponentRegistry::with_core(), Upcasters::new()).unwrap()
    }

    /// Creates one entity on every tick divisible by `every`.
    struct Spawner {
        every: u64,
    }

    impl System for Spawner {
        fn name(&self) -> &'static str {
            "spawner"
        }

        fn run(&mut self, world: &Arc<World>, tick: u64) -> Result<Vec<Event>, String> {
            if !tick.is_multiple_of(self.every) {
                return Ok(Vec::new());
            }
            Ok(vec![Event::EntityCreated(EntityCreated {
                id: world.next_entity_id(),
            })])
        }
    }

    /// Names the newest entity after the tick; relies on running after `Spawner`.
    struct Namer;

    impl System for Namer {
        fn name(&self) -> &'static str {
            "namer"
        }

        fn run(&mut self, world: &Arc<World>, tick: u64) -> Result<Vec<Event>, String> {
            let newest = EntityId(world.next_entity_id().0 - 1);
            if !world.contains(newest) || world.get::<Describable>(newest).is_some() {
                return Ok(Vec::new());
            }
            Ok(vec![Event::ComponentSet(ComponentSet {
                id: newest,
                component: Describable::NAME.into(),
                component_version: Describable::VERSION,
                data: serde_json::to_value(Describable {
                    name: format!("born at {tick}"),
                    description: String::new(),
                })
                .unwrap(),
            })])
        }
    }

    /// Always proposes an event on a missing entity.
    struct Broken;

    impl System for Broken {
        fn name(&self) -> &'static str {
            "broken"
        }

        fn run(&mut self, _: &Arc<World>, _: u64) -> Result<Vec<Event>, String> {
            Ok(vec![Event::EntityDestroyed(crate::EntityDestroyed {
                id: EntityId(999),
            })])
        }
    }

    /// Fails on its second run; counts how often it ran.
    struct Flaky {
        runs: Arc<std::sync::atomic::AtomicU32>,
    }

    impl System for Flaky {
        fn name(&self) -> &'static str {
            "flaky"
        }

        fn run(&mut self, _: &Arc<World>, _: u64) -> Result<Vec<Event>, String> {
            let n = self.runs.fetch_add(1, std::sync::atomic::Ordering::SeqCst) + 1;
            if n == 2 {
                Err("gave up".into())
            } else {
                Ok(Vec::new())
            }
        }
    }

    #[test]
    fn failed_system_is_suspended_and_the_world_keeps_ticking() {
        let mut journal = open(MemoryLog::default());
        let mut scheduler = Scheduler::new(&journal, 100);
        let runs = Arc::new(std::sync::atomic::AtomicU32::new(0));
        scheduler
            .add(Flaky {
                runs: Arc::clone(&runs),
            })
            .add(Spawner { every: 1 });
        let reports: Vec<StepReport> = (0..4)
            .map(|_| scheduler.step(&mut journal).unwrap())
            .collect();
        assert!(reports[0].suspended.is_empty());
        assert_eq!(
            reports[1].suspended,
            [SystemSuspended {
                system: "flaky",
                reason: "gave up".into()
            }]
        );
        assert!(reports[2].suspended.is_empty());
        assert_eq!(runs.load(std::sync::atomic::Ordering::SeqCst), 2);
        assert_eq!(scheduler.suspended(), ["flaky"]);
        assert_eq!(journal.world().len(), 4, "spawner kept running every tick");
    }

    #[test]
    fn systems_run_in_order_and_see_earlier_systems_this_tick() {
        let mut journal = open(MemoryLog::default());
        let mut scheduler = Scheduler::new(&journal, 100);
        scheduler.add(Spawner { every: 1 }).add(Namer);
        let report = scheduler.step(&mut journal).unwrap();
        assert_eq!(report.committed, ["spawner", "namer"]);
        assert_eq!(
            journal
                .world()
                .get::<Describable>(EntityId(1))
                .unwrap()
                .name,
            "born at 1"
        );
    }

    #[test]
    fn refused_system_is_reported_and_others_still_run() {
        let mut journal = open(MemoryLog::default());
        let mut scheduler = Scheduler::new(&journal, 100);
        scheduler.add(Broken).add(Spawner { every: 1 });
        let report = scheduler.step(&mut journal).unwrap();
        assert_eq!(report.committed, ["spawner"]);
        assert_eq!(
            report.refused,
            [SystemRefused {
                system: "broken",
                index: 0,
                error: ApplyError::NoSuchEntity(EntityId(999)),
            }]
        );
    }

    #[test]
    fn idle_world_checkpoints_the_clock() {
        let mut journal = open(MemoryLog::default());
        let mut scheduler = Scheduler::new(&journal, 4);
        let checkpoints: Vec<u64> = (0..10)
            .map(|_| scheduler.step(&mut journal).unwrap())
            .filter(|r| r.checkpoint)
            .map(|r| r.tick)
            .collect();
        assert_eq!(checkpoints, [4, 8]);
        assert_eq!(journal.world().tick(), 8);
    }

    #[test]
    fn activity_postpones_the_checkpoint() {
        let mut journal = open(MemoryLog::default());
        let mut scheduler = Scheduler::new(&journal, 4);
        scheduler.add(Spawner { every: 3 });
        let checkpoints: Vec<u64> = (0..12)
            .map(|_| scheduler.step(&mut journal).unwrap())
            .filter(|r| r.checkpoint)
            .map(|r| r.tick)
            .collect();
        assert!(checkpoints.is_empty(), "{checkpoints:?}");
    }

    #[test]
    fn record_clock_saves_idle_ticks_once() {
        let mut journal = open(MemoryLog::default());
        let mut scheduler = Scheduler::new(&journal, 100);
        for _ in 0..7 {
            scheduler.step(&mut journal).unwrap();
        }
        assert!(scheduler.record_clock(&mut journal).unwrap());
        assert!(!scheduler.record_clock(&mut journal).unwrap());
        assert_eq!(Scheduler::new(&open(journal.into_log()), 100).tick(), 7);
    }

    #[test]
    fn restart_resumes_from_the_last_recorded_tick() {
        let mut journal = open(MemoryLog::default());
        let mut scheduler = Scheduler::new(&journal, 4);
        for _ in 0..10 {
            scheduler.step(&mut journal).unwrap();
        }
        let log = journal.into_log();
        let reopened = open(log);
        let resumed = Scheduler::new(&reopened, 4);
        assert_eq!(resumed.tick(), 8, "ticks 9-10 were idle and unrecorded");
    }
}
