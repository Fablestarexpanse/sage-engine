//! Choosing which memories matter now: recency, importance and relevance, as in Generative
//! Agents (Park et al. 2023), each scaled to 0..1 and added with equal weight.
//!
//! Importance here is deterministic rules (owner ruling), so zero-AI worlds get meaningful
//! retrieval and the score is reproducible from the log.

use std::collections::BTreeSet;

use sage_core::{EntityId, Occurred, World};
use serde_json::Value;

use crate::mind::Mind;

/// Ticks for a memory's recency to halve: 2400 ticks is ten minutes at 4 Hz.
pub const RECENCY_HALF_LIFE: f64 = 2400.0;

/// Memories chosen by score for a prompt.
pub const RETRIEVED: usize = 10;

/// The most recent memories always included, whatever their score.
pub const ALWAYS_RECENT: usize = 5;

/// The most important older memories always included, so a message aimed at the agent is not
/// buried under chatter that merely resembles what is happening now.
pub const ALWAYS_IMPORTANT: usize = 3;

/// How much `agent` should care about `occurred`, from 0 to 10. A mind's `importance` weights,
/// keyed by occurrence kind, replace the rules for that kind.
pub fn importance(world: &World, agent: EntityId, mind: &Mind, occurred: &Occurred) -> f64 {
    if let Some(weight) = mind.importance.get(&occurred.kind) {
        return *weight;
    }
    let mine = occurred.actor == Some(agent);
    if occurred.kind == "sage.mind.reflected" && mine {
        return 7.0;
    }
    if mine {
        return if occurred.kind == "sage.command" {
            1.0
        } else {
            2.0
        };
    }
    if occurred.targets.contains(&agent) {
        return 8.0;
    }
    if let Some(text) = occurred.data.get("text").and_then(Value::as_str) {
        let named = world
            .name_of(agent)
            .is_some_and(|name| mentions(text, &name));
        return if named { 6.0 } else { 4.0 };
    }
    if occurred.kind == "sage.travelled" {
        return 2.0;
    }
    3.0
}

/// Whether `text` contains `name` as a whole word, ignoring case.
fn mentions(text: &str, name: &str) -> bool {
    let name = name.to_lowercase();
    words(text).any(|w| w == name)
}

fn words(text: &str) -> impl Iterator<Item = String> + '_ {
    text.split(|c: char| !c.is_alphanumeric())
        .filter(|w| !w.is_empty())
        .map(str::to_lowercase)
}

/// Words too common to signal relevance, including the verbs the core lexicon puts in almost
/// every line. English only: word overlap is the fallback when no embedding endpoint is set,
/// and embeddings are what work across languages.
const STOPWORDS: &[&str] = &[
    "about", "and", "are", "arrives", "but", "for", "from", "has", "have", "how", "into", "leaves",
    "not", "says", "tells", "that", "the", "this", "was", "what", "who", "with", "you", "your",
];

/// Word-overlap relevance from 0 to 1: the cosine of the two texts' sets of words of three or
/// more letters, leaving out [`STOPWORDS`]. Deterministic; used when no embedding endpoint is
/// configured.
pub fn lexical_relevance(query: &str, text: &str) -> f64 {
    let set = |s: &str| -> BTreeSet<String> {
        words(s)
            .filter(|w| w.chars().count() >= 3 && !STOPWORDS.contains(&w.as_str()))
            .collect()
    };
    let (q, t) = (set(query), set(text));
    if q.is_empty() || t.is_empty() {
        return 0.0;
    }
    let shared = q.intersection(&t).count() as f64;
    shared / ((q.len() * t.len()) as f64).sqrt()
}

/// A memory offered for retrieval.
#[derive(Clone, Debug, PartialEq)]
pub struct Candidate {
    /// Tick it happened.
    pub tick: u64,
    /// How it reads to the agent, already made safe for the prompt.
    pub text: String,
    /// From [`importance`], 0 to 10.
    pub importance: f64,
}

/// Recency from 0 to 1: halves every [`RECENCY_HALF_LIFE`] ticks.
pub fn recency(tick: u64, now: u64) -> f64 {
    0.5_f64.powf(now.saturating_sub(tick) as f64 / RECENCY_HALF_LIFE)
}

/// Indices of the memories to show, oldest first: the [`ALWAYS_RECENT`] newest, the
/// [`ALWAYS_IMPORTANT`] most important of the rest, and the [`RETRIEVED`] best of the rest by
/// recency + importance + relevance. Candidates are oldest first, and `relevance[i]` belongs
/// to `candidates[i]`. Ties go to the newer memory.
pub fn select(candidates: &[Candidate], relevance: &[f64], now: u64) -> Vec<usize> {
    let recent_from = candidates.len().saturating_sub(ALWAYS_RECENT);
    let mut chosen: BTreeSet<usize> = (recent_from..candidates.len()).collect();
    let older = &candidates[..recent_from];
    let best = |score: &dyn Fn(usize, &Candidate) -> f64, take: usize| -> Vec<usize> {
        let mut scored: Vec<(f64, usize)> = older
            .iter()
            .enumerate()
            .map(|(i, c)| (score(i, c), i))
            .collect();
        scored.sort_by(|(a_score, a), (b_score, b)| b_score.total_cmp(a_score).then(b.cmp(a)));
        scored.into_iter().take(take).map(|(_, i)| i).collect()
    };
    chosen.extend(best(&|_, c| c.importance, ALWAYS_IMPORTANT));
    chosen.extend(best(
        &|i, c| {
            let relevance = relevance.get(i).copied().unwrap_or(0.0).clamp(0.0, 1.0);
            recency(c.tick, now) + c.importance / 10.0 + relevance
        },
        RETRIEVED,
    ));
    chosen.into_iter().collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn lexical_relevance_counts_shared_words() {
        assert_eq!(lexical_relevance("the ferry", "ferry"), 1.0);
        assert!(lexical_relevance("when does the ferry leave", "Bo says the ferry is late") > 0.3);
        assert_eq!(
            lexical_relevance("Ada says hello", "Bo says goodbye"),
            0.0,
            "a shared lexicon verb is not relevance"
        );
        assert_eq!(lexical_relevance("ferry", "bread and cheese"), 0.0);
        assert_eq!(lexical_relevance("", "anything"), 0.0);
        assert_eq!(
            lexical_relevance("Ferry, FERRY!", "ferry"),
            1.0,
            "case and punctuation do not matter"
        );
    }

    #[test]
    fn recency_halves_every_half_life() {
        assert_eq!(recency(100, 100), 1.0);
        assert!((recency(0, 2400) - 0.5).abs() < 1e-12);
        assert!((recency(0, 4800) - 0.25).abs() < 1e-12);
        assert_eq!(recency(200, 100), 1.0, "future ticks count as now");
    }

    fn candidate(tick: u64, importance: f64) -> Candidate {
        Candidate {
            tick,
            text: format!("memory at {tick}"),
            importance,
        }
    }

    #[test]
    fn select_keeps_the_newest_and_the_best_of_the_rest() {
        // 30 memories one tick apart; memory 3 is very important, memory 7 very relevant.
        let mut candidates: Vec<Candidate> = (0..30).map(|t| candidate(t, 1.0)).collect();
        candidates[3].importance = 10.0;
        let mut relevance = vec![0.0; 30];
        relevance[7] = 1.0;
        let chosen = select(&candidates, &relevance, 30);
        assert!(chosen.len() <= ALWAYS_RECENT + ALWAYS_IMPORTANT + RETRIEVED);
        assert!(chosen.contains(&3) && chosen.contains(&7));
        assert!((25..30).all(|i| chosen.contains(&i)));
        assert!(chosen.windows(2).all(|w| w[0] < w[1]), "oldest first");
        assert!(
            !chosen.contains(&0),
            "old, unimportant, irrelevant memories drop out"
        );
    }

    #[test]
    fn select_with_few_memories_takes_them_all() {
        let candidates: Vec<Candidate> = (0..4).map(|t| candidate(t, 1.0)).collect();
        assert_eq!(select(&candidates, &[], 10), [0, 1, 2, 3]);
    }
}
