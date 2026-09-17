//! Reflection with a stub model: an agent that has perceived enough draws conclusions, which
//! are logged as occurrences only it perceives, enter its memory, reach its next prompt, and
//! are not redone after a restart.

use std::collections::BTreeMap;
use std::io::{BufRead, BufReader, Read, Write};
use std::net::TcpListener;
use std::sync::{Arc, Mutex};
use std::time::Duration;

use sage_agents::llm::{HttpTransport, LlmConfig, Thinker};
use sage_agents::reflection::{REFLECTED, Reflections};
use sage_agents::{Agents, Collected, Mind};
use sage_core::{
    Actor, Component, ComponentSet, Describable, EntityCreated, EntityId, Event, EventLog, Journal,
    Located, Place, Scheduler, Upcasters,
};
use sage_store::SqliteLog;
use serde_json::{Value, json};

const BO: EntityId = EntityId(2);
const WREN: EntityId = EntityId(3);

/// Answers reflection requests with `reflections` and action requests with an empty command,
/// recording each request.
fn stub(reflections: &'static str) -> (String, Arc<Mutex<Vec<Value>>>) {
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let url = format!("http://{}/v1", listener.local_addr().unwrap());
    let seen = Arc::new(Mutex::new(Vec::new()));
    let record = Arc::clone(&seen);
    std::thread::spawn(move || {
        for stream in listener.incoming() {
            let Ok(mut stream) = stream else { return };
            let record = Arc::clone(&record);
            std::thread::spawn(move || {
                let mut reader = BufReader::new(stream.try_clone().unwrap());
                let mut length = 0;
                loop {
                    let mut line = String::new();
                    if reader.read_line(&mut line).unwrap_or(0) == 0 {
                        return;
                    }
                    let line = line.trim_end().to_ascii_lowercase();
                    if line.is_empty() {
                        break;
                    }
                    if let Some(v) = line.strip_prefix("content-length:") {
                        length = v.trim().parse().unwrap();
                    }
                }
                let mut body = vec![0; length];
                reader.read_exact(&mut body).unwrap();
                let body: Value = serde_json::from_slice(&body).unwrap();
                let content = if body["response_format"]["json_schema"]["name"] == "reflections" {
                    reflections.to_owned()
                } else {
                    json!({"command": ""}).to_string()
                };
                record.lock().unwrap().push(body);
                let reply = json!({"choices": [{"message": {"content": content}}]}).to_string();
                let _ = write!(
                    stream,
                    "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{reply}",
                    reply.len()
                );
            });
        }
    });
    (url, seen)
}

fn set<C: Component>(id: EntityId, c: &C) -> Event {
    Event::ComponentSet(ComponentSet {
        id,
        component: C::NAME.into(),
        component_version: C::VERSION,
        data: serde_json::to_value(c).unwrap(),
    })
}

fn wren(driver: &str) -> Mind {
    Mind {
        driver: driver.into(),
        think_every: 2,
        persona: "A careful listener.".into(),
        goals: vec![],
        rules: vec![],
        importance: BTreeMap::new(),
        reflect_threshold: Some(20.0),
    }
}

/// A Hall (1) with Bo (2), a player, and Wren (3).
fn seed(journal: &mut Journal<SqliteLog>, mind: &Mind) {
    let named = |name: &str| Describable {
        name: name.into(),
        description: String::new(),
    };
    journal
        .commit(
            0,
            &[
                Event::EntityCreated(EntityCreated { id: EntityId(1) }),
                Event::EntityCreated(EntityCreated { id: BO }),
                Event::EntityCreated(EntityCreated { id: WREN }),
                set(EntityId(1), &Place {}),
                set(EntityId(1), &named("Hall")),
                set(BO, &named("Bo")),
                set(BO, &Actor {}),
                set(
                    BO,
                    &Located {
                        within: EntityId(1),
                    },
                ),
                set(WREN, &named("Wren")),
                set(WREN, &Actor {}),
                set(
                    WREN,
                    &Located {
                        within: EntityId(1),
                    },
                ),
                set(WREN, mind),
            ],
        )
        .unwrap();
}

fn open(log: SqliteLog) -> Journal<SqliteLog> {
    Journal::open(log, sage_agents::registry(), Upcasters::core()).unwrap()
}

struct World {
    journal: Journal<SqliteLog>,
    scheduler: Scheduler,
    agents: Agents,
    reflections: Reflections,
    collected: Vec<Collected>,
}

fn start(journal: Journal<SqliteLog>, url: &str) -> World {
    let mut scheduler = Scheduler::new(&journal, 1000);
    let reflections = Reflections::new();
    scheduler.add(reflections.clone());
    let config = LlmConfig {
        url: url.into(),
        model: "stub".into(),
        api_key: None,
        timeout: Duration::from_secs(5),
        workers: 1,
    };
    let agents = Agents::rebuild(journal.log(), &Upcasters::core())
        .unwrap()
        .with_verbs(scheduler.commands_mut().verbs())
        .with_thinker(Thinker::start(HttpTransport::new(config), 1));
    World {
        journal,
        scheduler,
        agents,
        reflections,
        collected: Vec::new(),
    }
}

impl World {
    fn run(&mut self, ticks: u64, player: &[(u64, &str)]) {
        for _ in 0..ticks {
            let next = self.scheduler.tick() + 1;
            for (tick, text) in player {
                if *tick == next {
                    self.scheduler.submit(BO, *text);
                }
            }
            let report = self.scheduler.step(&mut self.journal).unwrap();
            self.agents.observe(&report);
            let now = self.scheduler.tick() + 1;
            for thought in self.agents.think(self.journal.world(), now) {
                self.scheduler.submit(thought.agent, thought.command);
            }
            let collected = self.agents.collect(self.journal.world(), now);
            for (agent, text) in &collected.reflections {
                self.reflections.push(*agent, text.clone());
            }
            self.collected.push(collected);
            std::thread::sleep(Duration::from_millis(3));
        }
    }

    fn reflections_logged(&self) -> Vec<(Vec<u64>, String)> {
        self.journal
            .log()
            .read_page(1, 100_000)
            .unwrap()
            .into_iter()
            .filter(|e| e.record.event_type == "Occurred" && e.record.payload["kind"] == REFLECTED)
            .map(|e| {
                let audience = e.record.payload["audience"]
                    .as_array()
                    .unwrap()
                    .iter()
                    .map(|v| v.as_u64().unwrap())
                    .collect();
                (
                    audience,
                    e.record.payload["data"]["text"]
                        .as_str()
                        .unwrap()
                        .to_owned(),
                )
            })
            .collect()
    }
}

fn reflection_requests(seen: &Arc<Mutex<Vec<Value>>>) -> Vec<Value> {
    seen.lock()
        .unwrap()
        .iter()
        .filter(|b| b["response_format"]["json_schema"]["name"] == "reflections")
        .cloned()
        .collect()
}

fn telling() -> Vec<(u64, &'static str)> {
    vec![
        (2, "say Wren, the north gate key is under the loose stone."),
        (4, "say Wren, do not tell the guard."),
        (6, "say Wren, meet me at the gate at dawn."),
        (8, "say Wren, bring a lantern."),
    ]
}

#[test]
fn enough_important_memories_lead_to_a_logged_private_reflection() {
    let (url, seen) =
        stub(r#"{"reflections": ["Bo trusts me with the gate.", "Something happens at dawn."]}"#);
    let mut journal = open(SqliteLog::open_in_memory().unwrap());
    seed(&mut journal, &wren("llm"));
    let mut world = start(journal, &url);

    world.run(120, &telling());

    let logged = world.reflections_logged();
    assert_eq!(
        logged,
        [
            (vec![3], "Bo trusts me with the gate.".to_owned()),
            (vec![3], "Something happens at dawn.".to_owned()),
        ],
        "only Wren perceives her reflections"
    );
    let requests = reflection_requests(&seen);
    assert_eq!(
        requests.len(),
        1,
        "four lines naming Wren (6 each) pass 20 once"
    );
    let prompt = requests[0]["messages"][1]["content"].as_str().unwrap();
    assert!(prompt.contains("loose stone"), "{prompt}");
    assert!(prompt.ends_with("What does Wren conclude?"), "{prompt}");

    // Her next action prompt shows the reflection as a memory.
    let last_action = seen
        .lock()
        .unwrap()
        .iter()
        .rev()
        .find(|b| b["response_format"]["json_schema"]["name"] == "action")
        .cloned()
        .unwrap();
    let prompt = last_action["messages"][1]["content"].as_str().unwrap();
    assert!(
        prompt.contains("You think: Bo trusts me with the gate."),
        "{prompt}"
    );
}

#[test]
fn a_restart_does_not_reflect_on_the_same_memories_again() {
    let (url, seen) = stub(r#"{"reflections": ["Bo is planning something."]}"#);
    let mut journal = open(SqliteLog::open_in_memory().unwrap());
    seed(&mut journal, &wren("hybrid"));
    let mut world = start(journal, &url);
    world.run(80, &telling());
    assert_eq!(world.reflections_logged().len(), 1);
    assert_eq!(reflection_requests(&seen).len(), 1);

    let World { journal, .. } = world;
    let mut restarted = start(open(journal.into_log()), &url);
    restarted.run(60, &[]);
    assert_eq!(
        reflection_requests(&seen).len(),
        1,
        "memory says it already reflected"
    );
    assert_eq!(restarted.reflections_logged().len(), 1);
}

#[test]
fn a_refused_reflection_backs_off_instead_of_asking_again_every_think() {
    let (url, seen) = stub(r#"{"reflections": ["one", "two", "three", "four"]}"#);
    let mut journal = open(SqliteLog::open_in_memory().unwrap());
    seed(&mut journal, &wren("llm"));
    let mut world = start(journal, &url);
    world.run(90, &telling());

    assert!(world.reflections_logged().is_empty());
    assert_eq!(
        reflection_requests(&seen).len(),
        1,
        "backing off for 100 ticks"
    );
    let failed: Vec<String> = world
        .collected
        .iter()
        .flat_map(|c| c.failed.iter().map(|(_, why)| why.clone()))
        .collect();
    assert!(
        failed
            .iter()
            .any(|f| f.contains("refused: expected 1 to 3 reflections, got 4")),
        "{failed:?}"
    );
}

#[test]
fn scripted_minds_never_reflect() {
    let (url, seen) = stub(r#"{"reflections": ["unused"]}"#);
    let mut journal = open(SqliteLog::open_in_memory().unwrap());
    seed(&mut journal, &wren("scripted"));
    let mut world = start(journal, &url);
    world.run(60, &telling());
    assert!(seen.lock().unwrap().is_empty());
    assert!(world.reflections_logged().is_empty());
}
