//! The journal: the only path that changes a world. Apply, append, and undo if the append
//! fails.

use std::sync::Arc;

use thiserror::Error;

use crate::component::ComponentRegistry;
use crate::event::{DecodeError, Event, EventRecord};
use crate::upcast::Upcasters;
use crate::world::{ApplyError, SNAPSHOT_SCHEMA_VERSION, Snapshot, SnapshotError, World};

/// How many events replay reads from the log at a time.
pub const REPLAY_PAGE: usize = 4096;

/// An event as read back from a log.
#[derive(Clone, Debug, PartialEq)]
pub struct StoredEvent {
    /// Position in the log, starting at 1 with no gaps.
    pub seq: u64,
    /// World tick the event belongs to.
    pub tick: u64,
    /// The event.
    pub record: EventRecord,
}

/// A snapshot as stored in a log.
#[derive(Clone, Debug, PartialEq)]
pub struct StoredSnapshot {
    /// Sequence number of the last event the snapshot includes.
    pub seq: u64,
    /// Snapshot format version.
    pub schema_version: u32,
    /// Bytes from [`Snapshot::to_bytes`].
    pub bytes: Vec<u8>,
}

/// Durable, append-only storage for events and snapshots.
pub trait EventLog {
    /// Storage error.
    type Error: std::error::Error + Send + Sync + 'static;

    /// Atomically appends `events` as `first_seq..`. Must refuse if the log's last sequence
    /// number is not `first_seq - 1`, so two writers cannot interleave.
    fn append(
        &mut self,
        first_seq: u64,
        tick: u64,
        events: &[EventRecord],
    ) -> Result<(), Self::Error>;

    /// Up to `limit` events with `seq >= from`, in order. Replay reads the log in pages of
    /// [`REPLAY_PAGE`] so memory stays bounded however long the log is.
    fn read_page(&self, from: u64, limit: usize) -> Result<Vec<StoredEvent>, Self::Error>;

    /// Stores a snapshot.
    fn save_snapshot(&mut self, snapshot: &StoredSnapshot) -> Result<(), Self::Error>;

    /// The snapshot with the highest `seq`, if any.
    fn latest_snapshot(&self) -> Result<Option<StoredSnapshot>, Self::Error>;
}

/// Why a journal operation failed.
#[derive(Debug, Error)]
pub enum JournalError {
    /// The log failed.
    #[error("event log: {0}")]
    Log(Box<dyn std::error::Error + Send + Sync>),
    /// A batch was refused before anything was written.
    #[error("event {index} in batch refused: {error}")]
    Refused {
        /// Position in the batch.
        index: usize,
        /// Reason.
        error: ApplyError,
    },
    /// A stored event could not be read.
    #[error("event {seq}: {error}")]
    Decode {
        /// Sequence number.
        seq: u64,
        /// Reason.
        error: DecodeError,
    },
    /// A stored event is not valid against the world rebuilt so far.
    #[error("event {seq} does not apply to the log before it: {error}")]
    Corrupt {
        /// Sequence number.
        seq: u64,
        /// Reason.
        error: ApplyError,
    },
    /// The log skips or repeats a sequence number.
    #[error("log expected event {expected} but found {found}")]
    Gap {
        /// Expected sequence number.
        expected: u64,
        /// Found sequence number.
        found: u64,
    },
    /// A stored snapshot could not be restored.
    #[error("snapshot at {seq}: {error}")]
    Snapshot {
        /// Snapshot sequence number.
        seq: u64,
        /// Reason.
        error: SnapshotError,
    },
}

/// Owns a world and its log. Every change goes through [`Journal::commit`].
pub struct Journal<L: EventLog> {
    log: L,
    world: Arc<World>,
    upcasters: Upcasters,
}

impl<L: EventLog> Journal<L> {
    /// Opens a world from `log`: restores the latest snapshot, then replays later events.
    pub fn open(
        log: L,
        registry: ComponentRegistry,
        upcasters: Upcasters,
    ) -> Result<Self, JournalError> {
        let world = match log.latest_snapshot().map_err(log_error)? {
            Some(stored) => {
                let snapshot_error = |error| JournalError::Snapshot {
                    seq: stored.seq,
                    error,
                };
                if stored.schema_version != SNAPSHOT_SCHEMA_VERSION {
                    return Err(snapshot_error(SnapshotError::Version(
                        stored.schema_version,
                    )));
                }
                let snapshot = Snapshot::from_bytes(&stored.bytes).map_err(snapshot_error)?;
                World::restore(registry, &snapshot).map_err(snapshot_error)?
            }
            None => World::empty(registry),
        };
        Self::replay(log, world, upcasters)
    }

    /// Opens a world by replaying the whole log and ignoring snapshots.
    pub fn open_from_genesis(
        log: L,
        registry: ComponentRegistry,
        upcasters: Upcasters,
    ) -> Result<Self, JournalError> {
        Self::replay(log, World::empty(registry), upcasters)
    }

    fn replay(log: L, mut world: World, upcasters: Upcasters) -> Result<Self, JournalError> {
        loop {
            let page = log
                .read_page(world.last_seq() + 1, REPLAY_PAGE)
                .map_err(log_error)?;
            let full = page.len() == REPLAY_PAGE;
            for stored in page {
                let expected = world.last_seq() + 1;
                if stored.seq != expected {
                    return Err(JournalError::Gap {
                        expected,
                        found: stored.seq,
                    });
                }
                let event = Event::from_record(&stored.record, &upcasters).map_err(|error| {
                    JournalError::Decode {
                        seq: stored.seq,
                        error,
                    }
                })?;
                world
                    .apply_batch(stored.seq, stored.tick, std::slice::from_ref(&event))
                    .map_err(|(_, error)| JournalError::Corrupt {
                        seq: stored.seq,
                        error,
                    })?;
            }
            if !full {
                break;
            }
        }
        Ok(Journal {
            log,
            world: Arc::new(world),
            upcasters,
        })
    }

    /// The current world.
    pub fn world(&self) -> &World {
        &self.world
    }

    /// A shared handle to the current world, for systems that must hold the world for the
    /// length of their run (a plugin's store cannot hold a borrow). Every clone must be
    /// dropped before the next [`Journal::commit`], which panics otherwise.
    pub fn world_handle(&self) -> &Arc<World> {
        &self.world
    }

    fn world_mut(&mut self) -> &mut World {
        Arc::get_mut(&mut self.world)
            .expect("a world handle outlived the system run that borrowed it")
    }

    /// The upcasters used when reading the log.
    pub fn upcasters(&self) -> &Upcasters {
        &self.upcasters
    }

    /// The underlying log.
    pub fn log(&self) -> &L {
        &self.log
    }

    /// Applies `events` to the world, appends them to the log in one transaction, and undoes
    /// the world change if the append fails. Either both change or neither does. Returns the
    /// sequence number of the last event; an empty batch changes nothing.
    pub fn commit(&mut self, tick: u64, events: &[Event]) -> Result<u64, JournalError> {
        self.commit_events(tick, events)?;
        Ok(self.world.last_seq())
    }

    /// [`Journal::commit`], returning the events as stored: every occurrence carries the
    /// audience that perceived it, computed from the world after the whole batch applied.
    /// A proposed occurrence that already names an audience is refused.
    pub fn commit_events(
        &mut self,
        tick: u64,
        events: &[Event],
    ) -> Result<Vec<Event>, JournalError> {
        if events.is_empty() {
            return Ok(Vec::new());
        }
        for (index, event) in events.iter().enumerate() {
            if let Event::Occurred(occurred) = event
                && !occurred.audience.is_empty()
            {
                return Err(JournalError::Refused {
                    index,
                    error: ApplyError::BadOccurrence {
                        kind: occurred.kind.clone(),
                        reason: "audience is filled in by the journal; propose it empty".into(),
                    },
                });
            }
        }
        let first_seq = self.world.last_seq() + 1;
        let undo = self
            .world_mut()
            .apply_batch(first_seq, tick, events)
            .map_err(|(index, error)| JournalError::Refused { index, error })?;
        let mut stored = events.to_vec();
        for event in &mut stored {
            if let Event::Occurred(occurred) = event {
                occurred.audience = self.world.audience(occurred);
            }
        }
        let records: Vec<EventRecord> = stored.iter().map(Event::to_record).collect();
        if let Err(error) = self.log.append(first_seq, tick, &records) {
            self.world_mut().undo(undo);
            return Err(log_error(error));
        }
        Ok(stored)
    }

    /// Saves a snapshot of the current world to the log.
    pub fn save_snapshot(&mut self) -> Result<(), JournalError> {
        let stored = StoredSnapshot {
            seq: self.world.last_seq(),
            schema_version: SNAPSHOT_SCHEMA_VERSION,
            bytes: self.world.snapshot().to_bytes(),
        };
        self.log.save_snapshot(&stored).map_err(log_error)
    }

    /// Gives back the log, dropping the in-memory world.
    pub fn into_log(self) -> L {
        self.log
    }
}

fn log_error<E: std::error::Error + Send + Sync + 'static>(e: E) -> JournalError {
    JournalError::Log(Box::new(e))
}

#[cfg(test)]
pub(crate) mod test_log {
    use std::fmt;

    use super::*;

    /// In-memory log for core tests. `fail_appends` makes every append fail.
    #[derive(Default)]
    pub(crate) struct MemoryLog {
        pub(crate) events: Vec<StoredEvent>,
        pub(crate) snapshots: Vec<StoredSnapshot>,
        pub(crate) fail_appends: bool,
    }

    #[derive(Debug)]
    pub(crate) struct Refused;

    impl fmt::Display for Refused {
        fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
            f.write_str("append refused")
        }
    }

    impl std::error::Error for Refused {}

    impl EventLog for MemoryLog {
        type Error = Refused;

        fn append(
            &mut self,
            first_seq: u64,
            tick: u64,
            events: &[EventRecord],
        ) -> Result<(), Refused> {
            if self.fail_appends || first_seq != self.events.len() as u64 + 1 {
                return Err(Refused);
            }
            for (offset, record) in events.iter().enumerate() {
                self.events.push(StoredEvent {
                    seq: first_seq + offset as u64,
                    tick,
                    record: record.clone(),
                });
            }
            Ok(())
        }

        fn read_page(&self, from: u64, limit: usize) -> Result<Vec<StoredEvent>, Refused> {
            Ok(self
                .events
                .iter()
                .filter(|e| e.seq >= from)
                .take(limit)
                .cloned()
                .collect())
        }

        fn save_snapshot(&mut self, snapshot: &StoredSnapshot) -> Result<(), Refused> {
            self.snapshots.push(snapshot.clone());
            Ok(())
        }

        fn latest_snapshot(&self) -> Result<Option<StoredSnapshot>, Refused> {
            Ok(self.snapshots.last().cloned())
        }
    }
}

#[cfg(test)]
mod tests {
    use super::test_log::MemoryLog;
    use super::*;
    use crate::{Describable, EntityCreated, EntityId};

    #[test]
    fn failed_append_undoes_the_world() {
        let mut journal = Journal::open(
            MemoryLog::default(),
            ComponentRegistry::with_core(),
            Upcasters::core(),
        )
        .unwrap();
        let id = journal.world().next_entity_id();
        journal
            .commit(1, &[Event::EntityCreated(EntityCreated { id })])
            .unwrap();
        let before = journal.world().snapshot().to_bytes();

        journal.log.fail_appends = true;
        let next = EntityId(id.0 + 1);
        let err = journal
            .commit(
                2,
                &[
                    Event::EntityCreated(EntityCreated { id: next }),
                    Event::ComponentSet(crate::ComponentSet {
                        id,
                        component: "sage.describable".into(),
                        component_version: 1,
                        data: serde_json::to_value(Describable {
                            name: "x".into(),
                            description: "y".into(),
                        })
                        .unwrap(),
                    }),
                ],
            )
            .unwrap_err();
        assert!(matches!(err, JournalError::Log(_)));
        assert_eq!(journal.world().snapshot().to_bytes(), before);
        assert_eq!(journal.world().tick(), 1);
        assert_eq!(journal.log.events.len(), 1);
    }

    #[test]
    fn replay_crosses_page_boundaries() {
        let mut journal = Journal::open(
            MemoryLog::default(),
            ComponentRegistry::with_core(),
            Upcasters::core(),
        )
        .unwrap();
        // Exactly two full pages plus one event, committed in uneven batches.
        let total = REPLAY_PAGE * 2 + 1;
        let mut next = 1u64;
        while (next as usize) <= total {
            let batch: Vec<Event> = (next..next + 1000)
                .take(total + 1 - next as usize)
                .map(|id| Event::EntityCreated(EntityCreated { id: EntityId(id) }))
                .collect();
            next += batch.len() as u64;
            journal.commit(next, &batch).unwrap();
        }
        let live = journal.world().snapshot().to_bytes();
        let replayed = Journal::open_from_genesis(
            journal.into_log(),
            ComponentRegistry::with_core(),
            Upcasters::core(),
        )
        .unwrap();
        assert_eq!(replayed.world().last_seq(), total as u64);
        assert_eq!(replayed.world().snapshot().to_bytes(), live);
    }

    #[test]
    fn replay_refuses_a_gap_in_the_log() {
        let mut log = MemoryLog::default();
        for seq in [1, 3] {
            log.events.push(StoredEvent {
                seq,
                tick: 0,
                record: Event::EntityCreated(EntityCreated { id: EntityId(seq) }).to_record(),
            });
        }
        let err = Journal::open(log, ComponentRegistry::with_core(), Upcasters::core())
            .err()
            .unwrap();
        assert!(
            matches!(
                err,
                JournalError::Gap {
                    expected: 2,
                    found: 3
                }
            ),
            "{err}"
        );
    }

    #[test]
    fn empty_commit_writes_nothing() {
        let mut journal = Journal::open(
            MemoryLog::default(),
            ComponentRegistry::with_core(),
            Upcasters::core(),
        )
        .unwrap();
        assert_eq!(journal.commit(5, &[]).unwrap(), 0);
        assert_eq!(journal.world().tick(), 0);
        assert!(journal.log.events.is_empty());
    }
}
