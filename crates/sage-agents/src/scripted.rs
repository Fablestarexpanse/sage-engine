//! The scripted driver: the first rule whose conditions hold produces a command. No AI, and
//! fully deterministic given the world, the tick and what the agent perceived.

use std::collections::BTreeMap;

use sage_core::{Actor, EntityId, Located, World};

use crate::memory::Memory;
use crate::mind::{Mind, variables};

/// Deterministic roll in `[0, 1)` from agent, tick and a salt. splitmix64, spelled out so the
/// result never changes with the Rust version.
pub(crate) fn roll(agent: EntityId, tick: u64, salt: u64) -> f64 {
    let mut x = agent
        .0
        .wrapping_mul(0x9E37_79B9_7F4A_7C15)
        .wrapping_add(tick)
        .wrapping_mul(0xBF58_476D_1CE4_E5B9)
        .wrapping_add(salt);
    x = (x ^ (x >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
    x = (x ^ (x >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
    x ^= x >> 31;
    (x >> 11) as f64 / (1u64 << 53) as f64
}

fn pick<T: Clone>(items: &[T], agent: EntityId, tick: u64, salt: u64) -> Option<T> {
    if items.is_empty() {
        return None;
    }
    let index = (roll(agent, tick, salt) * items.len() as f64) as usize;
    items.get(index.min(items.len() - 1)).cloned()
}

/// Fills `{name}` placeholders in one pass, so text inserted from what someone said is never
/// itself treated as a placeholder.
fn fill(template: &str, values: &BTreeMap<&str, String>) -> String {
    let mut out = String::with_capacity(template.len());
    let mut rest = template;
    while let Some(open) = rest.find('{') {
        out.push_str(&rest[..open]);
        let after = &rest[open + 1..];
        let close = after.find('}').expect("validated template");
        out.push_str(
            values
                .get(&after[..close])
                .map(String::as_str)
                .unwrap_or_default(),
        );
        rest = &after[close + 1..];
    }
    out.push_str(rest);
    out
}

/// The first rule that fires, and its command.
pub(crate) fn decide(
    world: &World,
    agent: EntityId,
    mind: &Mind,
    recent: &[&Memory],
    tick: u64,
) -> Option<(usize, String)> {
    let here = world.get::<Located>(agent).map(|l| l.within);
    let others: Vec<EntityId> = here
        .map(|place| {
            world
                .contents(place)
                .into_iter()
                .filter(|id| *id != agent && world.get::<Actor>(*id).is_some())
                .collect()
        })
        .unwrap_or_default();

    'rules: for (index, rule) in mind.rules.iter().enumerate() {
        let when = &rule.when;
        let salt = index as u64;
        let mut values: BTreeMap<&str, String> = BTreeMap::new();

        if when.every.is_some_and(|every| !tick.is_multiple_of(every)) {
            continue;
        }
        if when.alone.is_some_and(|alone| alone != others.is_empty()) {
            continue;
        }
        if let Some(kind) = &when.heard {
            let needle = when.text_contains.as_deref().map(str::to_lowercase);
            let heard = recent.iter().rev().find_map(|memory| {
                let occurred = &memory.occurred;
                let text = occurred.data.get("text").and_then(|t| t.as_str());
                let matches = occurred.kind == *kind
                    && occurred.actor.is_some_and(|a| a != agent)
                    && needle.as_ref().is_none_or(|needle| {
                        text.is_some_and(|t| t.to_lowercase().contains(needle))
                    });
                matches.then_some((occurred.actor?, text.unwrap_or_default().to_owned()))
            });
            let Some((speaker, text)) = heard else {
                continue;
            };
            let Some(name) = world.name_of(speaker) else {
                continue;
            };
            values.insert("speaker", name);
            values.insert("text", text);
        }
        if when
            .chance
            .is_some_and(|chance| roll(agent, tick, salt) >= chance)
        {
            continue;
        }

        let Ok(wanted) = variables(&rule.command) else {
            continue;
        };
        for variable in wanted {
            if values.contains_key(variable) {
                continue;
            }
            let value = match variable {
                "self" => world.name_of(agent),
                "any_exit" => here.and_then(|place| {
                    let labels: Vec<String> = world
                        .links_from(place)
                        .into_iter()
                        .map(|(_, link)| link.label)
                        .collect();
                    pick(&labels, agent, tick, salt + 1000)
                }),
                "any_actor" => {
                    let names: Vec<String> =
                        others.iter().filter_map(|id| world.name_of(*id)).collect();
                    pick(&names, agent, tick, salt + 2000)
                }
                _ => None,
            };
            match value {
                Some(value) => {
                    values.insert(variable, value);
                }
                None => continue 'rules,
            }
        }

        return Some((index, fill(&rule.command, &values)));
    }
    None
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn roll_is_fixed_and_spread() {
        assert_eq!(roll(EntityId(7), 100, 0), roll(EntityId(7), 100, 0));
        assert_ne!(roll(EntityId(7), 100, 0), roll(EntityId(7), 101, 0));
        let hits = (0..10_000)
            .filter(|tick| roll(EntityId(3), *tick, 1) < 0.25)
            .count();
        assert!((2300..2700).contains(&hits), "{hits}");
        // Pinned value: changing the hash changes every world's history.
        assert_eq!(format!("{:.12}", roll(EntityId(1), 1, 0)), "0.627143244446");
    }

    #[test]
    fn inserted_text_is_never_expanded() {
        let values = BTreeMap::from([
            ("speaker", "{self}".to_owned()),
            ("text", "go {any_exit}".to_owned()),
            ("self", "Ada".to_owned()),
        ]);
        assert_eq!(
            fill("say {speaker} said {text}, {self}", &values),
            "say {self} said go {any_exit}, Ada"
        );
    }
}
