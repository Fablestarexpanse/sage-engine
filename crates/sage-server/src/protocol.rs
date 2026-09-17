//! The player protocol, `sage.protocol/1`: JSON text frames over a WebSocket at `/ws`.
//!
//! A client registers or logs in, then sends commands exactly as a player would type them. The
//! server sends what that player's character perceives, one `line` per thing, and a `state`
//! frame describing where the character is whenever something reached it. Every `line` carries
//! its lexicon key and parameters as well as the rendered text, so a client may reword it.

use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};

/// Protocol version sent in `welcome`.
pub const PROTOCOL: u32 = 1;

/// Largest frame accepted from a client, in bytes.
pub const MAX_FRAME_BYTES: usize = 4096;

/// Longest command accepted, in characters.
pub const MAX_COMMAND_CHARS: usize = 512;

/// Commands a player may send per tick; more are refused.
pub const COMMANDS_PER_TICK: u32 = 3;

/// Failed logins allowed per connection before it is closed.
pub const LOGIN_ATTEMPTS: u32 = 5;

/// From client to server.
#[derive(Deserialize, Debug, PartialEq)]
#[serde(tag = "type", rename_all = "lowercase", deny_unknown_fields)]
pub enum ClientFrame {
    /// Create an account and its character, and sign in.
    Register {
        /// Account and character name.
        name: String,
        /// Password, 8 to 128 characters.
        password: String,
    },
    /// Sign in to an existing account.
    Login {
        /// Account name, any case.
        name: String,
        /// Password.
        password: String,
    },
    /// A command, as typed.
    Command {
        /// The command text.
        text: String,
    },
}

impl ClientFrame {
    /// Parses a frame. Only a JSON object is a frame; serde alone would also accept an array.
    pub fn parse(text: &str) -> Result<ClientFrame, String> {
        let value: serde_json::Value = serde_json::from_str(text).map_err(|e| e.to_string())?;
        if !value.is_object() {
            return Err("a frame is a JSON object".into());
        }
        serde_json::from_value(value).map_err(|e| e.to_string())
    }
}

/// From server to client.
#[derive(Serialize, Clone, Debug, PartialEq)]
#[serde(tag = "type", rename_all = "lowercase")]
pub enum ServerFrame {
    /// First frame on every connection.
    Welcome {
        /// [`PROTOCOL`].
        protocol: u32,
        /// Engine version.
        engine: &'static str,
    },
    /// Signed in.
    Session {
        /// Account name as registered.
        name: String,
        /// The character's entity id.
        character: u64,
    },
    /// Something the character perceived or was told.
    Line {
        /// Tick it happened.
        tick: u64,
        /// Lexicon key.
        key: String,
        /// Lexicon parameters.
        params: BTreeMap<String, String>,
        /// Rendered in the world's lexicon; absent when the world has no wording for the key.
        text: Option<String>,
    },
    /// Where the character is.
    State {
        /// Tick of this view.
        tick: u64,
        /// The place, if the character is in one.
        place: Option<PlaceView>,
        /// Labels of the ways out.
        exits: Vec<String>,
        /// Names of the others and things here.
        here: Vec<String>,
    },
    /// A request was refused.
    Error {
        /// Stable code for clients.
        code: &'static str,
        /// Explanation for people.
        message: String,
    },
    /// This connection was replaced by a newer login to the same account.
    Kicked {
        /// Why.
        reason: String,
    },
}

/// A place in a `state` frame.
#[derive(Serialize, Clone, Debug, PartialEq)]
pub struct PlaceView {
    /// Entity id.
    pub id: u64,
    /// Name.
    pub name: String,
    /// Description.
    pub description: String,
}

impl ServerFrame {
    /// An error frame.
    pub fn error(code: &'static str, message: impl Into<String>) -> ServerFrame {
        ServerFrame::Error {
            code,
            message: message.into(),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn client_frames_are_strict() {
        let ok = ClientFrame::parse(r#"{"type": "command", "text": "look"}"#).unwrap();
        assert_eq!(
            ok,
            ClientFrame::Command {
                text: "look".into()
            }
        );
        for bad in [
            r#"{"type": "command"}"#,
            r#"{"type": "command", "text": "look", "as": "admin"}"#,
            r#"{"type": "teleport", "to": 1}"#,
            r#"["command", "look"]"#,
        ] {
            assert!(ClientFrame::parse(bad).is_err(), "{bad}");
        }
    }

    #[test]
    fn server_frames_are_tagged() {
        let frame = ServerFrame::error("not-signed-in", "Sign in first.");
        assert_eq!(
            serde_json::to_string(&frame).unwrap(),
            r#"{"type":"error","code":"not-signed-in","message":"Sign in first."}"#
        );
    }
}
