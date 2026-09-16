//! Core events and their versioned on-disk form.

use serde::{Deserialize, Serialize, de::DeserializeOwned};
use serde_json::Value;
use thiserror::Error;

use crate::upcast::{UpcastError, Upcasters};
use crate::world::EntityId;

/// A single event type's payload.
pub trait EventPayload: Serialize + DeserializeOwned {
    /// Stable type name stored in the log.
    const TYPE: &'static str;
    /// Current schema version of the payload. Starts at 1; bump it and register an upcaster
    /// whenever the shape changes.
    const VERSION: u32;
}

/// An entity came into existence.
#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
pub struct EntityCreated {
    /// The new entity.
    pub id: EntityId,
}

impl EventPayload for EntityCreated {
    const TYPE: &'static str = "EntityCreated";
    const VERSION: u32 = 1;
}

/// An entity and all its components are gone.
#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
pub struct EntityDestroyed {
    /// The removed entity.
    pub id: EntityId,
}

impl EventPayload for EntityDestroyed {
    const TYPE: &'static str = "EntityDestroyed";
    const VERSION: u32 = 1;
}

/// A component was added to an entity or replaced.
#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
pub struct ComponentSet {
    /// Target entity.
    pub id: EntityId,
    /// Registered component name.
    pub component: String,
    /// Schema version of `data`.
    pub component_version: u32,
    /// Serialized component.
    pub data: Value,
}

impl EventPayload for ComponentSet {
    const TYPE: &'static str = "ComponentSet";
    const VERSION: u32 = 1;
}

/// A component was removed from an entity.
#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
pub struct ComponentRemoved {
    /// Target entity.
    pub id: EntityId,
    /// Registered component name.
    pub component: String,
}

impl EventPayload for ComponentRemoved {
    const TYPE: &'static str = "ComponentRemoved";
    const VERSION: u32 = 1;
}

/// Time passed with nothing else happening. The scheduler records one every few ticks while a
/// world is idle, so a restart loses at most that many ticks of world time. The tick itself is
/// stored with the event, so the payload is empty.
#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
pub struct ClockAdvanced {}

impl EventPayload for ClockAdvanced {
    const TYPE: &'static str = "ClockAdvanced";
    const VERSION: u32 = 1;
}

/// Something happened that changes no component: speech, travel, a command being issued.
/// Occurrences are what actors perceive, and what agent memory is built from.
#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
pub struct Occurred {
    /// Namespaced kind, e.g. `sage.said`. A plugin's kinds start with its fragment id.
    pub kind: String,
    /// Schema version of `data` for this kind. Starts at 1.
    pub kind_version: u32,
    /// Who did it, if anyone.
    pub actor: Option<EntityId>,
    /// Places where it can be perceived, in a meaningful order (e.g. from, then to).
    pub places: Vec<EntityId>,
    /// Entities it is directed at; they perceive it wherever they are.
    pub targets: Vec<EntityId>,
    /// Kind-specific details.
    pub data: Value,
    /// Every actor that perceived it, in id order. Proposals leave this empty; the journal
    /// fills it in when the occurrence commits, so memory is an exact projection of the log.
    /// Empty for occurrences stored before v2.
    pub audience: Vec<EntityId>,
}

impl EventPayload for Occurred {
    const TYPE: &'static str = "Occurred";
    const VERSION: u32 = 2;
}

/// Every core event.
#[derive(Clone, Debug, PartialEq)]
pub enum Event {
    /// See [`EntityCreated`].
    EntityCreated(EntityCreated),
    /// See [`EntityDestroyed`].
    EntityDestroyed(EntityDestroyed),
    /// See [`ComponentSet`].
    ComponentSet(ComponentSet),
    /// See [`ComponentRemoved`].
    ComponentRemoved(ComponentRemoved),
    /// See [`ClockAdvanced`].
    ClockAdvanced(ClockAdvanced),
    /// See [`Occurred`].
    Occurred(Occurred),
}

/// An event as persisted: type name, schema version and JSON payload.
#[derive(Clone, Debug, PartialEq)]
pub struct EventRecord {
    /// Event type name.
    pub event_type: String,
    /// Schema version of `payload`. Never 0.
    pub schema_version: u32,
    /// Payload at `schema_version`.
    pub payload: Value,
}

/// Why a stored record could not become an [`Event`].
#[derive(Debug, Error)]
pub enum DecodeError {
    /// The type name is not a known event.
    #[error("unknown event type `{0}`")]
    UnknownType(String),
    /// The record has no schema version.
    #[error("event `{0}` has schema version 0; every stored event must be versioned")]
    Unversioned(String),
    /// The payload could not be upcast.
    #[error(transparent)]
    Upcast(#[from] UpcastError),
    /// The upcast payload does not match the current shape.
    #[error("event `{event_type}` payload does not match v{version}: {source}")]
    Shape {
        /// Event type.
        event_type: String,
        /// Version the payload was expected to match.
        version: u32,
        /// Deserialization error.
        source: serde_json::Error,
    },
}

impl Event {
    /// Type name of this event.
    pub fn event_type(&self) -> &'static str {
        match self {
            Event::EntityCreated(_) => EntityCreated::TYPE,
            Event::EntityDestroyed(_) => EntityDestroyed::TYPE,
            Event::ComponentSet(_) => ComponentSet::TYPE,
            Event::ComponentRemoved(_) => ComponentRemoved::TYPE,
            Event::ClockAdvanced(_) => ClockAdvanced::TYPE,
            Event::Occurred(_) => Occurred::TYPE,
        }
    }

    /// The persisted form, always at the current schema version.
    pub fn to_record(&self) -> EventRecord {
        fn record<P: EventPayload>(payload: &P) -> EventRecord {
            EventRecord {
                event_type: P::TYPE.to_owned(),
                schema_version: P::VERSION,
                payload: serde_json::to_value(payload).expect("core events serialize to JSON"),
            }
        }
        match self {
            Event::EntityCreated(p) => record(p),
            Event::EntityDestroyed(p) => record(p),
            Event::ComponentSet(p) => record(p),
            Event::ComponentRemoved(p) => record(p),
            Event::ClockAdvanced(p) => record(p),
            Event::Occurred(p) => record(p),
        }
    }

    /// Reads a stored record, upcasting old payloads to the current shape.
    pub fn from_record(record: &EventRecord, upcasters: &Upcasters) -> Result<Event, DecodeError> {
        fn decode<P: EventPayload>(
            record: &EventRecord,
            upcasters: &Upcasters,
        ) -> Result<P, DecodeError> {
            let payload = upcasters.upcast(
                P::TYPE,
                record.schema_version,
                P::VERSION,
                record.payload.clone(),
            )?;
            serde_json::from_value(payload).map_err(|source| DecodeError::Shape {
                event_type: P::TYPE.to_owned(),
                version: P::VERSION,
                source,
            })
        }

        if record.schema_version == 0 {
            return Err(DecodeError::Unversioned(record.event_type.clone()));
        }
        Ok(match record.event_type.as_str() {
            EntityCreated::TYPE => Event::EntityCreated(decode(record, upcasters)?),
            EntityDestroyed::TYPE => Event::EntityDestroyed(decode(record, upcasters)?),
            ComponentSet::TYPE => Event::ComponentSet(decode(record, upcasters)?),
            ComponentRemoved::TYPE => Event::ComponentRemoved(decode(record, upcasters)?),
            ClockAdvanced::TYPE => Event::ClockAdvanced(decode(record, upcasters)?),
            Occurred::TYPE => Event::Occurred(decode(record, upcasters)?),
            other => return Err(DecodeError::UnknownType(other.to_owned())),
        })
    }
}

#[cfg(test)]
mod tests {
    use serde_json::json;

    use super::*;

    fn all_events() -> Vec<Event> {
        let id = EntityId(3);
        vec![
            Event::EntityCreated(EntityCreated { id }),
            Event::EntityDestroyed(EntityDestroyed { id }),
            Event::ComponentSet(ComponentSet {
                id,
                component: "sage.place".into(),
                component_version: 1,
                data: json!({}),
            }),
            Event::ComponentRemoved(ComponentRemoved {
                id,
                component: "sage.place".into(),
            }),
            Event::ClockAdvanced(ClockAdvanced {}),
            Event::Occurred(Occurred {
                kind: "sage.said".into(),
                kind_version: 1,
                actor: Some(id),
                places: vec![EntityId(1)],
                targets: vec![],
                data: json!({"text": "hi"}),
                audience: vec![id],
            }),
        ]
    }

    #[test]
    fn every_event_round_trips_through_its_record() {
        for event in all_events() {
            let record = event.to_record();
            assert!(record.schema_version > 0);
            assert_eq!(
                Event::from_record(&record, &Upcasters::new()).unwrap(),
                event
            );
        }
    }

    #[test]
    fn refuses_unversioned_record() {
        let mut record = all_events()[0].to_record();
        record.schema_version = 0;
        let err = Event::from_record(&record, &Upcasters::new()).unwrap_err();
        assert!(matches!(err, DecodeError::Unversioned(_)));
    }

    #[test]
    fn refuses_unknown_type() {
        let record = EventRecord {
            event_type: "Teleported".into(),
            schema_version: 1,
            payload: json!({}),
        };
        let err = Event::from_record(&record, &Upcasters::new()).unwrap_err();
        assert!(matches!(err, DecodeError::UnknownType(_)));
    }

    #[test]
    fn refuses_record_from_newer_engine() {
        let mut record = all_events()[0].to_record();
        record.schema_version = 2;
        let err = Event::from_record(&record, &Upcasters::new()).unwrap_err();
        assert!(matches!(
            err,
            DecodeError::Upcast(UpcastError::FromNewerEngine { .. })
        ));
    }

    #[test]
    fn refuses_wrong_shape() {
        let record = EventRecord {
            event_type: "EntityCreated".into(),
            schema_version: 1,
            payload: json!({"entity": 3}),
        };
        let err = Event::from_record(&record, &Upcasters::new()).unwrap_err();
        assert!(matches!(err, DecodeError::Shape { .. }));
    }
}
