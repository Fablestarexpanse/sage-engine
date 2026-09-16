//! The `sage` binary. Server, WebSocket transport and CLI land at M4; until then it only
//! reports its version.

fn main() {
    match std::env::args().nth(1).as_deref() {
        Some("--version") | Some("-V") | None => println!("sage {}", env!("CARGO_PKG_VERSION")),
        Some(other) => {
            eprintln!("sage: unknown argument `{other}` (only --version exists before M1)");
            std::process::exit(2);
        }
    }
}
