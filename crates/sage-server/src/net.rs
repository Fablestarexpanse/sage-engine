//! The network side of play: a WebSocket server on its own thread and tokio runtime.
//!
//! It parses frames, enforces frame size and login attempts, and does the slow argon2 work,
//! then hands each request to the engine thread as an [`Inbound`] message. It never touches the
//! world. Everything a player sees comes back from the engine through that session's channel.

use std::net::SocketAddr;
use std::path::PathBuf;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::mpsc::Sender;
use std::sync::{Arc, Mutex};

use axum::Router;
use axum::extract::State;
use axum::extract::ws::{Message, WebSocket, WebSocketUpgrade};
use axum::response::Response;
use axum::routing::get;
use futures_util::{SinkExt, StreamExt};
use tokio::sync::mpsc::{UnboundedSender, unbounded_channel};

use crate::accounts::{self, Accounts};
use crate::protocol::{ClientFrame, LOGIN_ATTEMPTS, MAX_FRAME_BYTES, PROTOCOL, ServerFrame};

/// A request from a connection to the engine thread.
pub enum Inbound {
    /// A connection opened; frames for it go to `out`.
    Connected {
        /// Connection id.
        session: u64,
        /// Where to send frames.
        out: UnboundedSender<ServerFrame>,
    },
    /// The connection closed.
    Disconnected {
        /// Connection id.
        session: u64,
    },
    /// Create an account and character. The password is already hashed.
    Register {
        /// Connection id.
        session: u64,
        /// Requested name, already checked for form.
        name: String,
        /// argon2id hash.
        password_hash: String,
    },
    /// The password for `name` was verified.
    LoggedIn {
        /// Connection id.
        session: u64,
        /// Account name as given.
        name: String,
    },
    /// A command from a signed-in player.
    Command {
        /// Connection id.
        session: u64,
        /// As typed.
        text: String,
    },
}

#[derive(Clone)]
struct Shared {
    to_engine: Arc<Mutex<Sender<Inbound>>>,
    accounts: Arc<Mutex<Accounts>>,
    next_session: Arc<AtomicU64>,
    /// A real hash of a throwaway password, checked when a name does not exist so a failed
    /// login takes as long either way.
    dummy_hash: Arc<String>,
}

impl Shared {
    fn send(&self, message: Inbound) {
        let _ = self.to_engine.lock().expect("engine channel").send(message);
    }
}

/// Starts the server on `listen` and returns the address it is bound to.
pub fn start(
    listen: &str,
    accounts_path: PathBuf,
    to_engine: Sender<Inbound>,
) -> Result<SocketAddr, String> {
    let accounts =
        Accounts::open(&accounts_path).map_err(|e| format!("{}: {e}", accounts_path.display()))?;
    let shared = Shared {
        to_engine: Arc::new(Mutex::new(to_engine)),
        accounts: Arc::new(Mutex::new(accounts)),
        next_session: Arc::new(AtomicU64::new(1)),
        dummy_hash: Arc::new(accounts::hash_password("not a real password")?),
    };
    let listen = listen.to_owned();
    let (bound_tx, bound_rx) = std::sync::mpsc::channel();
    std::thread::Builder::new()
        .name("sage-net".into())
        .spawn(move || {
            let runtime = match tokio::runtime::Builder::new_multi_thread()
                .worker_threads(2)
                .enable_all()
                .build()
            {
                Ok(runtime) => runtime,
                Err(e) => {
                    let _ = bound_tx.send(Err(e.to_string()));
                    return;
                }
            };
            runtime.block_on(async move {
                let listener = match tokio::net::TcpListener::bind(&listen).await {
                    Ok(listener) => listener,
                    Err(e) => {
                        let _ = bound_tx.send(Err(format!("cannot listen on {listen}: {e}")));
                        return;
                    }
                };
                let _ = bound_tx.send(listener.local_addr().map_err(|e| e.to_string()));
                let app = Router::new().route("/ws", get(upgrade)).with_state(shared);
                if let Err(e) = axum::serve(listener, app).await {
                    eprintln!("network server stopped: {e}");
                }
            });
        })
        .map_err(|e| e.to_string())?;
    bound_rx
        .recv()
        .map_err(|_| "network thread ended before binding".to_owned())?
}

async fn upgrade(ws: WebSocketUpgrade, State(shared): State<Shared>) -> Response {
    ws.max_message_size(MAX_FRAME_BYTES)
        .max_frame_size(MAX_FRAME_BYTES)
        .on_upgrade(move |socket| connection(socket, shared))
}

async fn connection(socket: WebSocket, shared: Shared) {
    let session = shared.next_session.fetch_add(1, Ordering::SeqCst);
    let (mut sink, mut stream) = socket.split();
    let (out, mut outgoing) = unbounded_channel::<ServerFrame>();

    let writer = tokio::spawn(async move {
        while let Some(frame) = outgoing.recv().await {
            let kicked = matches!(frame, ServerFrame::Kicked { .. });
            let text = serde_json::to_string(&frame).expect("frames serialize");
            if sink.send(Message::Text(text.into())).await.is_err() {
                return;
            }
            if kicked {
                break;
            }
        }
        let _ = sink.send(Message::Close(None)).await;
    });

    let _ = out.send(ServerFrame::Welcome {
        protocol: PROTOCOL,
        engine: env!("CARGO_PKG_VERSION"),
    });
    shared.send(Inbound::Connected {
        session,
        out: out.clone(),
    });

    let mut failed_logins = 0;
    while let Some(Ok(message)) = stream.next().await {
        let text = match message {
            Message::Text(text) => text,
            Message::Close(_) => break,
            Message::Binary(_) => {
                let _ = out.send(ServerFrame::error("bad-frame", "Frames are JSON text."));
                continue;
            }
            _ => continue,
        };
        let frame = match ClientFrame::parse(text.as_str()) {
            Ok(frame) => frame,
            Err(e) => {
                let _ = out.send(ServerFrame::error("bad-frame", e));
                continue;
            }
        };
        match frame {
            ClientFrame::Command { text } => shared.send(Inbound::Command { session, text }),
            ClientFrame::Register { name, password } => {
                if let Err(message) =
                    accounts::check_name(&name).and_then(|()| accounts::check_password(&password))
                {
                    let _ = out.send(ServerFrame::error("bad-registration", message));
                    continue;
                }
                match tokio::task::spawn_blocking(move || accounts::hash_password(&password)).await
                {
                    Ok(Ok(password_hash)) => shared.send(Inbound::Register {
                        session,
                        name,
                        password_hash,
                    }),
                    _ => {
                        let _ = out.send(ServerFrame::error(
                            "server-error",
                            "The password could not be stored.",
                        ));
                    }
                }
            }
            ClientFrame::Login { name, password } => {
                let stored = shared
                    .accounts
                    .lock()
                    .expect("accounts lock")
                    .password_hash(&name)
                    .unwrap_or(None);
                let verified = match stored {
                    // Hash anyway on an unknown name, so timing does not reveal which names exist.
                    None => {
                        let dummy = Arc::clone(&shared.dummy_hash);
                        let _ = tokio::task::spawn_blocking(move || {
                            accounts::verify_password(&password, &dummy)
                        })
                        .await;
                        false
                    }
                    Some(stored) => tokio::task::spawn_blocking(move || {
                        accounts::verify_password(&password, &stored)
                    })
                    .await
                    .unwrap_or(false),
                };
                if verified {
                    shared.send(Inbound::LoggedIn { session, name });
                } else {
                    failed_logins += 1;
                    let _ = out.send(ServerFrame::error(
                        "bad-login",
                        "That name and password do not match.",
                    ));
                    if failed_logins >= LOGIN_ATTEMPTS {
                        break;
                    }
                }
            }
        }
    }

    // Let queued frames (such as the last error) go out: the writer ends once the engine has
    // dropped this session, which it does on the next tick.
    shared.send(Inbound::Disconnected { session });
    drop(out);
    if tokio::time::timeout(std::time::Duration::from_secs(2), writer)
        .await
        .is_err()
    {
        // The engine is not ticking; give up on a graceful close.
    }
}
