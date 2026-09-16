//! Event log and snapshots on SQLite (WAL). The single source of truth: in-memory state is a
//! projection of this log, never a second store.

use std::path::Path;

use rusqlite::{Connection, OptionalExtension, params};
use sage_core::{EventLog, EventRecord, StoredEvent, StoredSnapshot};
use thiserror::Error;

/// Version of the SQLite schema below, kept in `PRAGMA user_version`.
pub const STORE_SCHEMA_VERSION: i64 = 1;

const SCHEMA: &str = "
CREATE TABLE events (
    seq            INTEGER PRIMARY KEY CHECK (seq > 0),
    tick           INTEGER NOT NULL CHECK (tick >= 0),
    event_type     TEXT    NOT NULL CHECK (length(event_type) > 0),
    schema_version INTEGER NOT NULL CHECK (schema_version > 0),
    payload        TEXT    NOT NULL CHECK (json_valid(payload))
) STRICT;

CREATE TRIGGER events_no_update BEFORE UPDATE ON events
BEGIN SELECT RAISE(ABORT, 'events are append-only'); END;

CREATE TRIGGER events_no_delete BEFORE DELETE ON events
BEGIN SELECT RAISE(ABORT, 'events are append-only'); END;

CREATE TABLE snapshots (
    seq            INTEGER PRIMARY KEY CHECK (seq >= 0),
    schema_version INTEGER NOT NULL CHECK (schema_version > 0),
    body           BLOB    NOT NULL
) STRICT;

PRAGMA user_version = 1;
";

/// Store errors.
#[derive(Debug, Error)]
pub enum StoreError {
    /// SQLite failed or refused a write.
    #[error(transparent)]
    Sqlite(#[from] rusqlite::Error),
    /// The file was written by a newer engine.
    #[error(
        "store schema v{found} is newer than this engine (reads up to v{STORE_SCHEMA_VERSION})"
    )]
    NewerSchema {
        /// Version found in the file.
        found: i64,
    },
    /// Another writer appended first.
    #[error("append expected the log to end at {expected} but it ends at {found}")]
    SeqConflict {
        /// Last sequence number the caller expected.
        expected: u64,
        /// Last sequence number in the log.
        found: u64,
    },
    /// A stored payload is not JSON (should be impossible given the CHECK constraint).
    #[error("event {seq} payload is not JSON: {source}")]
    Payload {
        /// Sequence number.
        seq: u64,
        /// Parse error.
        source: serde_json::Error,
    },
}

/// A world's event log in one SQLite file.
pub struct SqliteLog {
    conn: Connection,
    in_group: bool,
}

impl SqliteLog {
    /// Opens or creates the log at `path`.
    pub fn open(path: impl AsRef<Path>) -> Result<Self, StoreError> {
        Self::init(Connection::open(path)?)
    }

    /// An in-memory log, for tests and throwaway worlds.
    pub fn open_in_memory() -> Result<Self, StoreError> {
        Self::init(Connection::open_in_memory()?)
    }

    fn init(conn: Connection) -> Result<Self, StoreError> {
        conn.busy_timeout(std::time::Duration::from_secs(5))?;
        conn.pragma_update(None, "journal_mode", "WAL")?;
        conn.pragma_update(None, "synchronous", "FULL")?;
        let version: i64 = conn.pragma_query_value(None, "user_version", |row| row.get(0))?;
        match version {
            0 => conn.execute_batch(&format!("BEGIN;{SCHEMA}COMMIT;"))?,
            STORE_SCHEMA_VERSION => {}
            found => return Err(StoreError::NewerSchema { found }),
        }
        Ok(SqliteLog {
            conn,
            in_group: false,
        })
    }

    /// Direct access for tests that need to prove what the database itself refuses.
    #[doc(hidden)]
    pub fn connection(&self) -> &Connection {
        &self.conn
    }
}

fn to_i64(n: u64) -> i64 {
    i64::try_from(n).expect("sequence numbers and ticks fit in i64")
}

/// Checks the log ends at `first_seq - 1` and inserts `events` from there.
fn insert_batch(
    conn: &Connection,
    first_seq: u64,
    tick: u64,
    events: &[EventRecord],
) -> Result<(), StoreError> {
    let last: i64 = conn.query_row("SELECT COALESCE(MAX(seq), 0) FROM events", [], |r| r.get(0))?;
    let last = last as u64;
    if last + 1 != first_seq {
        return Err(StoreError::SeqConflict {
            expected: first_seq - 1,
            found: last,
        });
    }
    {
        let mut insert = conn.prepare_cached(
            "INSERT INTO events (seq, tick, event_type, schema_version, payload)
                 VALUES (?1, ?2, ?3, ?4, ?5)",
        )?;
        for (offset, record) in events.iter().enumerate() {
            insert.execute(params![
                to_i64(first_seq + offset as u64),
                to_i64(tick),
                record.event_type,
                record.schema_version,
                record.payload.to_string(),
            ])?;
        }
    }
    Ok(())
}

impl EventLog for SqliteLog {
    type Error = StoreError;

    fn append(
        &mut self,
        first_seq: u64,
        tick: u64,
        events: &[EventRecord],
    ) -> Result<(), StoreError> {
        // Inside a group the append is a savepoint of the group's transaction; otherwise it is
        // its own transaction. Either way it is all or nothing.
        if self.in_group {
            let savepoint = self.conn.savepoint()?;
            insert_batch(&savepoint, first_seq, tick, events)?;
            savepoint.commit()?;
        } else {
            let tx = self
                .conn
                .transaction_with_behavior(rusqlite::TransactionBehavior::Immediate)?;
            insert_batch(&tx, first_seq, tick, events)?;
            tx.commit()?;
        }
        Ok(())
    }

    fn begin_group(&mut self) -> Result<(), StoreError> {
        assert!(!self.in_group, "groups do not nest");
        self.conn.execute_batch("BEGIN IMMEDIATE")?;
        self.in_group = true;
        Ok(())
    }

    fn end_group(&mut self) -> Result<(), StoreError> {
        self.conn.execute_batch("COMMIT")?;
        self.in_group = false;
        Ok(())
    }

    fn abort_group(&mut self) -> Result<(), StoreError> {
        self.in_group = false;
        if !self.conn.is_autocommit() {
            self.conn.execute_batch("ROLLBACK")?;
        }
        Ok(())
    }

    fn read_page(&self, from: u64, limit: usize) -> Result<Vec<StoredEvent>, StoreError> {
        let mut stmt = self.conn.prepare_cached(
            "SELECT seq, tick, event_type, schema_version, payload
             FROM events WHERE seq >= ?1 ORDER BY seq LIMIT ?2",
        )?;
        let limit = i64::try_from(limit).unwrap_or(i64::MAX);
        let rows = stmt.query_map(params![to_i64(from), limit], |row| {
            Ok((
                row.get::<_, i64>(0)? as u64,
                row.get::<_, i64>(1)? as u64,
                row.get::<_, String>(2)?,
                row.get::<_, u32>(3)?,
                row.get::<_, String>(4)?,
            ))
        })?;
        rows.map(|row| {
            let (seq, tick, event_type, schema_version, payload) = row?;
            let payload = serde_json::from_str(&payload)
                .map_err(|source| StoreError::Payload { seq, source })?;
            Ok(StoredEvent {
                seq,
                tick,
                record: EventRecord {
                    event_type,
                    schema_version,
                    payload,
                },
            })
        })
        .collect()
    }

    fn save_snapshot(&mut self, snapshot: &StoredSnapshot) -> Result<(), StoreError> {
        self.conn.execute(
            "INSERT OR REPLACE INTO snapshots (seq, schema_version, body) VALUES (?1, ?2, ?3)",
            params![
                to_i64(snapshot.seq),
                snapshot.schema_version,
                snapshot.bytes
            ],
        )?;
        Ok(())
    }

    fn latest_snapshot(&self) -> Result<Option<StoredSnapshot>, StoreError> {
        Ok(self
            .conn
            .query_row(
                "SELECT seq, schema_version, body FROM snapshots ORDER BY seq DESC LIMIT 1",
                [],
                |row| {
                    Ok(StoredSnapshot {
                        seq: row.get::<_, i64>(0)? as u64,
                        schema_version: row.get(1)?,
                        bytes: row.get(2)?,
                    })
                },
            )
            .optional()?)
    }
}
