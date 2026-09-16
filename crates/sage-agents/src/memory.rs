//! Memory as a projection of the log. Every stored occurrence names its audience, so what an
//! actor remembers is exactly the occurrences whose audience includes it, in log order. The
//! same stream is built live from step reports and rebuilt from the log on restart.

use std::collections::{BTreeMap, VecDeque};

use sage_core::{EntityId, Event, EventLog, Occurred, REPLAY_PAGE, StepReport, Upcasters};

/// Most memories kept per actor; the oldest are dropped first, identically live and on rebuild.
pub const MEMORY_LIMIT: usize = 256;

/// One remembered occurrence.
#[derive(Clone, Debug, PartialEq)]
pub struct Memory {
    /// Tick it happened.
    pub tick: u64,
    /// What happened.
    pub occurred: Occurred,
}

/// Every actor's memory stream.
#[derive(Clone, Debug, Default, PartialEq)]
pub struct Memories {
    streams: BTreeMap<EntityId, VecDeque<Memory>>,
}

impl Memories {
    /// No memories.
    pub fn new() -> Memories {
        Memories::default()
    }

    /// Rebuilds every stream by reading the whole log.
    pub fn rebuild<L: EventLog>(log: &L, upcasters: &Upcasters) -> Result<Memories, String> {
        let mut memories = Memories::new();
        let mut from = 1;
        loop {
            let page = log
                .read_page(from, REPLAY_PAGE)
                .map_err(|e| e.to_string())?;
            let full = page.len() == REPLAY_PAGE;
            for stored in &page {
                if stored.record.event_type != "Occurred" {
                    continue;
                }
                match Event::from_record(&stored.record, upcasters) {
                    Ok(Event::Occurred(occurred)) => memories.record(stored.tick, &occurred),
                    Ok(_) => {}
                    Err(e) => return Err(format!("event {}: {e}", stored.seq)),
                }
            }
            match page.last() {
                Some(last) if full => from = last.seq + 1,
                _ => break,
            }
        }
        Ok(memories)
    }

    /// Adds `occurred` to the stream of everyone in its audience.
    pub fn record(&mut self, tick: u64, occurred: &Occurred) {
        for who in &occurred.audience {
            let stream = self.streams.entry(*who).or_default();
            stream.push_back(Memory {
                tick,
                occurred: occurred.clone(),
            });
            if stream.len() > MEMORY_LIMIT {
                stream.pop_front();
            }
        }
    }

    /// Adds every occurrence committed in a step. A step reports one delivery per audience
    /// member per occurrence, contiguously, so each occurrence is recorded once even if two
    /// identical ones happened.
    pub fn observe(&mut self, report: &StepReport) {
        let mut i = 0;
        while i < report.deliveries.len() {
            match &report.deliveries[i].occurred {
                Some(occurred) => {
                    self.record(report.tick, occurred);
                    i += occurred.audience.len().max(1);
                }
                None => i += 1,
            }
        }
    }

    /// `who`'s memories, oldest first.
    pub fn of(&self, who: EntityId) -> impl Iterator<Item = &Memory> {
        self.streams.get(&who).into_iter().flatten()
    }

    /// `who`'s memories from ticks `first..=last`, oldest first.
    pub fn between(&self, who: EntityId, first: u64, last: u64) -> Vec<&Memory> {
        self.of(who)
            .filter(|m| (first..=last).contains(&m.tick))
            .collect()
    }
}
