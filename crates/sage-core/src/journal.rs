//! The journal: the only path that changes a world. Check, append, then apply.

use thiserror::Error;

use crate::component::ComponentRegistry;
use crate::event::{DecodeError, Event, EventRecord};
use crate::upcast::Upcasters;
use crate::world::{ApplyError, SNAPSHOT_SCHEMA_VERSION, Snapshot, SnapshotError, World};

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

    /// Every event with `seq >= from`, in order.
    fn read_from(&self, from: u64) -> Result<Vec<StoredEvent>, Self::Error>;

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
    world: World,
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
        for stored in log.read_from(world.last_seq() + 1).map_err(log_error)? {
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
                .check_batch(std::slice::from_ref(&event))
                .map_err(|(_, error)| JournalError::Corrupt {
                    seq: stored.seq,
                    error,
                })?;
            world.apply_checked(stored.seq, stored.tick, &event);
        }
        Ok(Journal {
            log,
            world,
            upcasters,
        })
    }

    /// The current world.
    pub fn world(&self) -> &World {
        &self.world
    }

    /// The upcasters used when reading the log.
    pub fn upcasters(&self) -> &Upcasters {
        &self.upcasters
    }

    /// The underlying log.
    pub fn log(&self) -> &L {
        &self.log
    }

    /// Checks `events` against the world, appends them atomically, then applies them. If the
    /// check or the append fails, neither the log nor the world changes. Returns the sequence
    /// number of the last event.
    pub fn commit(&mut self, tick: u64, events: &[Event]) -> Result<u64, JournalError> {
        self.world
            .check_batch(events)
            .map_err(|(index, error)| JournalError::Refused { index, error })?;
        let first_seq = self.world.last_seq() + 1;
        let records: Vec<EventRecord> = events.iter().map(Event::to_record).collect();
        self.log
            .append(first_seq, tick, &records)
            .map_err(log_error)?;
        for (offset, event) in events.iter().enumerate() {
            self.world
                .apply_checked(first_seq + offset as u64, tick, event);
        }
        Ok(self.world.last_seq())
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
