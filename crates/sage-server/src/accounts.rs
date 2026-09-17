//! Player accounts: a name, an argon2id password hash, and the character they play.
//!
//! Accounts live in `<world>.accounts.db`, never in the event log, so password hashes are not
//! part of world history, replays or snapshots. Names are unique regardless of case.

use std::path::Path;

use argon2::Argon2;
use argon2::password_hash::phc::PasswordHash;
use argon2::password_hash::{PasswordHasher, PasswordVerifier};
use rusqlite::{Connection, OptionalExtension, params};

/// A stored account.
#[derive(Clone, Debug, PartialEq)]
pub struct Account {
    /// Name as registered.
    pub name: String,
    /// The character's entity id, if one exists.
    pub character: Option<u64>,
}

/// The accounts file.
pub struct Accounts {
    conn: Connection,
}

impl Accounts {
    /// Opens or creates `path`.
    pub fn open(path: impl AsRef<Path>) -> Result<Accounts, String> {
        let conn = Connection::open(path).map_err(|e| e.to_string())?;
        conn.busy_timeout(std::time::Duration::from_secs(5))
            .map_err(|e| e.to_string())?;
        conn.execute_batch(
            "PRAGMA journal_mode = WAL;
             CREATE TABLE IF NOT EXISTS accounts (
                 name          TEXT NOT NULL PRIMARY KEY COLLATE NOCASE,
                 password_hash TEXT NOT NULL,
                 character     INTEGER
             ) STRICT;",
        )
        .map_err(|e| e.to_string())?;
        Ok(Accounts { conn })
    }

    /// The account called `name`, in any case.
    pub fn find(&self, name: &str) -> Result<Option<Account>, String> {
        self.conn
            .query_row(
                "SELECT name, character FROM accounts WHERE name = ?1",
                [name],
                |row| {
                    Ok(Account {
                        name: row.get(0)?,
                        character: row.get::<_, Option<i64>>(1)?.map(|c| c as u64),
                    })
                },
            )
            .optional()
            .map_err(|e| e.to_string())
    }

    /// The stored hash for `name`, if the account exists.
    pub fn password_hash(&self, name: &str) -> Result<Option<String>, String> {
        self.conn
            .query_row(
                "SELECT password_hash FROM accounts WHERE name = ?1",
                [name],
                |row| row.get(0),
            )
            .optional()
            .map_err(|e| e.to_string())
    }

    /// Creates an account. Fails if the name is taken in any case.
    pub fn create(&self, name: &str, password_hash: &str, character: u64) -> Result<(), String> {
        self.conn
            .execute(
                "INSERT INTO accounts (name, password_hash, character) VALUES (?1, ?2, ?3)",
                params![name, password_hash, character as i64],
            )
            .map(|_| ())
            .map_err(|e| e.to_string())
    }

    /// Points `name` at a new character.
    pub fn set_character(&self, name: &str, character: u64) -> Result<(), String> {
        self.conn
            .execute(
                "UPDATE accounts SET character = ?1 WHERE name = ?2",
                params![character as i64, name],
            )
            .map(|_| ())
            .map_err(|e| e.to_string())
    }
}

/// Why a name or password is not acceptable, if it is not.
pub fn check_name(name: &str) -> Result<(), String> {
    let mut chars = name.chars();
    let first_is_letter = chars.next().is_some_and(|c| c.is_ascii_alphabetic());
    let rest_ok = chars.all(|c| c.is_ascii_alphanumeric() || c == '-');
    if !(2..=24).contains(&name.len()) || !first_is_letter || !rest_ok {
        return Err(
            "A name is 2 to 24 letters, digits or hyphens, and starts with a letter.".into(),
        );
    }
    Ok(())
}

/// Why a password is not acceptable, if it is not.
pub fn check_password(password: &str) -> Result<(), String> {
    if !(8..=128).contains(&password.chars().count()) {
        return Err("A password is 8 to 128 characters.".into());
    }
    Ok(())
}

/// An argon2id hash of `password` with a fresh random salt. Slow on purpose; call it off the
/// engine thread.
pub fn hash_password(password: &str) -> Result<String, String> {
    Argon2::default()
        .hash_password(password.as_bytes())
        .map(|hash| hash.to_string())
        .map_err(|e| e.to_string())
}

/// Whether `password` matches `stored`. Slow on purpose; call it off the engine thread.
pub fn verify_password(password: &str, stored: &str) -> bool {
    PasswordHash::new(stored)
        .map(|hash| {
            Argon2::default()
                .verify_password(password.as_bytes(), &hash)
                .is_ok()
        })
        .unwrap_or(false)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn names_and_passwords() {
        for good in ["Ada", "bo", "Night-Owl2"] {
            assert!(check_name(good).is_ok(), "{good}");
        }
        for bad in [
            "A",
            "2pac",
            "-dash",
            "has space",
            "émile",
            &"x".repeat(25),
            "",
        ] {
            assert!(check_name(bad).is_err(), "{bad}");
        }
        assert!(check_password("correct horse").is_ok());
        assert!(check_password("short").is_err());
        assert!(check_password(&"p".repeat(129)).is_err());
    }

    #[test]
    fn hashes_verify_and_differ_by_salt() {
        let a = hash_password("correct horse").unwrap();
        let b = hash_password("correct horse").unwrap();
        assert_ne!(a, b);
        assert!(a.starts_with("$argon2id$"));
        assert!(verify_password("correct horse", &a));
        assert!(!verify_password("wrong horse", &a));
        assert!(!verify_password("correct horse", "not a hash"));
    }

    #[test]
    fn names_are_unique_in_any_case() {
        let dir = tempfile::tempdir().unwrap();
        let accounts = Accounts::open(dir.path().join("a.db")).unwrap();
        accounts.create("Ada", "hash", 7).unwrap();
        assert!(accounts.create("ADA", "hash", 8).is_err());
        assert_eq!(
            accounts.find("aDa").unwrap(),
            Some(Account {
                name: "Ada".into(),
                character: Some(7)
            })
        );
        accounts.set_character("ada", 9).unwrap();
        assert_eq!(accounts.find("Ada").unwrap().unwrap().character, Some(9));
        assert_eq!(
            accounts.password_hash("ada").unwrap().as_deref(),
            Some("hash")
        );
    }
}
