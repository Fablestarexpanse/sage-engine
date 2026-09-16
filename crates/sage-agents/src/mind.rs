//! The `sage.mind` component.

use serde::{Deserialize, Serialize};

/// Drivers this engine can run.
pub const DRIVERS: [&str; 1] = ["scripted"];

/// Template variables a rule's command may use.
pub const VARIABLES: [&str; 5] = ["speaker", "text", "any_exit", "any_actor", "self"];

/// An agent's mind: how it decides, who it is, and (for the scripted driver) its rules.
#[derive(bevy_ecs::component::Component, Serialize, Deserialize, Clone, Debug, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Mind {
    /// Which driver decides: `scripted`.
    pub driver: String,
    /// Think once every this many ticks.
    pub think_every: u64,
    /// Who the agent is, in prose. Unused by the scripted driver; LLM drivers read it.
    #[serde(default)]
    pub persona: String,
    /// What the agent wants, in prose. Unused by the scripted driver.
    #[serde(default)]
    pub goals: Vec<String>,
    /// Scripted driver: tried in order; the first whose conditions all hold fires.
    #[serde(default)]
    pub rules: Vec<Rule>,
}

/// One scripted rule.
#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Rule {
    /// Conditions; all present ones must hold. No conditions means always.
    #[serde(default)]
    pub when: When,
    /// The command to submit. `{speaker}`, `{text}`, `{any_exit}`, `{any_actor}` and `{self}`
    /// are filled in; if one cannot be (no exit, nobody else here), the rule does not fire.
    #[serde(rename = "do")]
    pub command: String,
}

/// Conditions for a rule.
#[derive(Serialize, Deserialize, Clone, Debug, PartialEq, Default)]
#[serde(deny_unknown_fields)]
pub struct When {
    /// Someone else did an occurrence of this kind (e.g. `sage.said`) that the agent perceived
    /// since it last thought. The latest such occurrence sets `{speaker}` and `{text}`.
    pub heard: Option<String>,
    /// With `heard`: the occurrence's text contains this, ignoring case.
    pub text_contains: Option<String>,
    /// The tick is a multiple of this.
    pub every: Option<u64>,
    /// Fires with this probability, decided by a fixed hash of agent, tick and rule.
    pub chance: Option<f64>,
    /// Whether the agent must be the only actor in its place (`true`) or not (`false`).
    pub alone: Option<bool>,
}

impl sage_core::Component for Mind {
    const NAME: &'static str = "sage.mind";
    const VERSION: u32 = 1;

    fn validate(&self) -> Result<(), String> {
        if !DRIVERS.contains(&self.driver.as_str()) {
            return Err(format!(
                "driver `{}` is not one of {}",
                self.driver,
                DRIVERS.join(", ")
            ));
        }
        if self.think_every == 0 {
            return Err("think_every must be at least 1".into());
        }
        if self.persona.chars().count() > 4000 {
            return Err("persona is longer than 4000 characters".into());
        }
        if self.rules.len() > 64 {
            return Err("at most 64 rules".into());
        }
        for (i, rule) in self.rules.iter().enumerate() {
            let fail = |why: String| Err(format!("rules[{i}]: {why}"));
            let when = &rule.when;
            if when.every == Some(0) {
                return fail("every must be at least 1".into());
            }
            if let Some(chance) = when.chance
                && !(chance.is_finite() && (0.0..=1.0).contains(&chance))
            {
                return fail(format!("chance {chance} is not between 0 and 1"));
            }
            if when.text_contains.is_some() && when.heard.is_none() {
                return fail("text_contains needs heard".into());
            }
            if rule.command.trim().is_empty() {
                return fail("do must not be empty".into());
            }
            for variable in variables(&rule.command)? {
                if !VARIABLES.contains(&variable) {
                    return fail(format!(
                        "`{{{variable}}}` is not one of {}",
                        VARIABLES.map(|v| format!("{{{v}}}")).join(", ")
                    ));
                }
                if matches!(variable, "speaker" | "text") && when.heard.is_none() {
                    return fail(format!("`{{{variable}}}` needs heard"));
                }
            }
        }
        Ok(())
    }
}

/// The `{name}` variables in a command template, in order.
pub(crate) fn variables(template: &str) -> Result<Vec<&str>, String> {
    let mut found = Vec::new();
    let mut rest = template;
    while let Some(open) = rest.find('{') {
        let after = &rest[open + 1..];
        let close = after
            .find('}')
            .ok_or_else(|| format!("unclosed `{{` in `{template}`"))?;
        found.push(&after[..close]);
        rest = &after[close + 1..];
    }
    Ok(found)
}
