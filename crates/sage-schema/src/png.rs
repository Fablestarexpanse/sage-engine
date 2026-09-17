//! Just enough PNG to find and write text chunks. Pixels are never decoded.
//!
//! The reader treats every byte as hostile: lengths are unsigned and checked against what is
//! left, every chunk moves the cursor forward by at least 12 bytes, and nothing is allocated
//! from a length field. A crafted file ends in an error, never a hang or a panic.

use serde::Serialize;

/// The eight bytes every PNG starts with.
pub const SIGNATURE: [u8; 8] = [137, 80, 78, 71, 13, 10, 26, 10];

/// Largest chunk length the PNG specification allows.
pub const MAX_CHUNK_LEN: u32 = 0x7fff_ffff;

/// Why a file could not be read as PNG chunks.
#[derive(Serialize, Clone, Debug, PartialEq, Eq)]
#[serde(tag = "error", rename_all = "kebab-case")]
pub enum PngError {
    /// The file does not start with the PNG signature.
    NotPng,
    /// A chunk header or body runs past the end of the file.
    Truncated {
        /// Byte offset of the chunk.
        offset: usize,
    },
    /// A chunk claims more than [`MAX_CHUNK_LEN`] bytes.
    ChunkTooLong {
        /// Byte offset of the chunk.
        offset: usize,
        /// The claimed length.
        length: u32,
    },
    /// A chunk type is not four ASCII letters.
    BadChunkType {
        /// Byte offset of the chunk.
        offset: usize,
    },
    /// The first chunk is not `IHDR`.
    NoHeader,
}

impl std::fmt::Display for PngError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            PngError::NotPng => write!(f, "not a PNG file"),
            PngError::Truncated { offset } => write!(f, "chunk at byte {offset} is cut off"),
            PngError::ChunkTooLong { offset, length } => {
                write!(f, "chunk at byte {offset} claims {length} bytes")
            }
            PngError::BadChunkType { offset } => {
                write!(f, "chunk at byte {offset} has an invalid type")
            }
            PngError::NoHeader => write!(f, "the first chunk is not IHDR"),
        }
    }
}

/// One chunk, borrowed from the file.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Chunk<'a> {
    /// Byte offset of the chunk's length field.
    pub offset: usize,
    /// Chunk type, e.g. `tEXt`.
    pub kind: [u8; 4],
    /// Chunk data.
    pub data: &'a [u8],
    /// Whether the stored CRC matches.
    pub crc_ok: bool,
}

/// How reading the chunks ended.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Ending {
    /// At `IEND`, as a PNG should. Bytes after it are ignored.
    Iend,
    /// At the end of the file, with no `IEND`.
    NoIend,
    /// At a damaged chunk after `IHDR`; the chunks before it were read.
    Damaged(PngError),
}

/// The chunks up to and including `IEND`, strictly: a damaged chunk anywhere is an error. A
/// file with no `IEND` returns the chunks it has, and `false`.
pub fn chunks(bytes: &[u8]) -> Result<(Vec<Chunk<'_>>, bool), PngError> {
    match walk(bytes)? {
        (found, Ending::Iend) => Ok((found, true)),
        (found, Ending::NoIend) => Ok((found, false)),
        (_, Ending::Damaged(e)) => Err(e),
    }
}

/// The chunks up to and including `IEND`, stopping early at damage after the header. Only a
/// file that is not a PNG, or whose header chunk is damaged or missing, is an error.
pub fn walk(bytes: &[u8]) -> Result<(Vec<Chunk<'_>>, Ending), PngError> {
    if bytes.len() < SIGNATURE.len() || bytes[..SIGNATURE.len()] != SIGNATURE {
        return Err(PngError::NotPng);
    }
    let mut offset = SIGNATURE.len();
    let mut found = Vec::new();
    while offset < bytes.len() {
        match chunk_at(bytes, offset, found.is_empty()) {
            Ok(chunk) => {
                offset += 12 + chunk.data.len();
                let end = &chunk.kind == b"IEND";
                found.push(chunk);
                if end {
                    return Ok((found, Ending::Iend));
                }
            }
            Err(e) if found.is_empty() => return Err(e),
            Err(e) => return Ok((found, Ending::Damaged(e))),
        }
    }
    Ok((found, Ending::NoIend))
}

fn chunk_at(bytes: &[u8], offset: usize, first: bool) -> Result<Chunk<'_>, PngError> {
    let rest = &bytes[offset..];
    if rest.len() < 12 {
        return Err(PngError::Truncated { offset });
    }
    let length = u32::from_be_bytes([rest[0], rest[1], rest[2], rest[3]]);
    if length > MAX_CHUNK_LEN {
        return Err(PngError::ChunkTooLong { offset, length });
    }
    let length = length as usize;
    // 4 length + 4 type + data + 4 CRC; `rest.len() - 12` cannot underflow here.
    if length > rest.len() - 12 {
        return Err(PngError::Truncated { offset });
    }
    let kind = [rest[4], rest[5], rest[6], rest[7]];
    if !kind.iter().all(u8::is_ascii_alphabetic) {
        return Err(PngError::BadChunkType { offset });
    }
    if first && &kind != b"IHDR" {
        return Err(PngError::NoHeader);
    }
    let stored = u32::from_be_bytes([
        rest[8 + length],
        rest[9 + length],
        rest[10 + length],
        rest[11 + length],
    ]);
    Ok(Chunk {
        offset,
        kind,
        data: &rest[8..8 + length],
        crc_ok: crc32(&rest[4..8 + length]) == stored,
    })
}

/// How a text chunk stores its text.
#[derive(Serialize, Clone, Copy, Debug, PartialEq, Eq)]
pub enum TextKind {
    /// `tEXt`: Latin-1, uncompressed.
    #[serde(rename = "tEXt")]
    Text,
    /// `iTXt`: UTF-8, possibly compressed.
    #[serde(rename = "iTXt")]
    International,
    /// `zTXt`: Latin-1, compressed.
    #[serde(rename = "zTXt")]
    Compressed,
}

/// A text chunk.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct TextChunk<'a> {
    /// Byte offset of the chunk.
    pub offset: usize,
    /// Which text chunk type.
    pub kind: TextKind,
    /// The keyword, decoded as Latin-1.
    pub keyword: String,
    /// The text bytes, or `None` when compressed (compressed text is never inflated).
    pub text: Option<&'a [u8]>,
    /// Whether the stored CRC matches.
    pub crc_ok: bool,
}

/// Every well-formed text chunk, in file order. Text chunks without a keyword separator are
/// skipped.
/// Reading stops early at damage after the header, as [`walk`] does.
pub fn text_chunks(bytes: &[u8]) -> Result<(Vec<TextChunk<'_>>, Ending), PngError> {
    let (all, ending) = walk(bytes)?;
    let texts = all.iter().filter_map(text_chunk).collect();
    Ok((texts, ending))
}

fn text_chunk<'a>(chunk: &Chunk<'a>) -> Option<TextChunk<'a>> {
    let kind = match &chunk.kind {
        b"tEXt" => TextKind::Text,
        b"iTXt" => TextKind::International,
        b"zTXt" => TextKind::Compressed,
        _ => return None,
    };
    let nul = chunk.data.iter().position(|&b| b == 0)?;
    let keyword: String = chunk.data[..nul].iter().map(|&b| b as char).collect();
    let after = &chunk.data[nul + 1..];
    let text = match kind {
        TextKind::Text => Some(after),
        TextKind::Compressed => None,
        TextKind::International => {
            // compression flag, compression method, language tag\0, translated keyword\0, text
            let (&flag, rest) = after.split_first()?;
            let rest = rest.get(1..)?;
            let language_end = rest.iter().position(|&b| b == 0)?;
            let rest = &rest[language_end + 1..];
            let translated_end = rest.iter().position(|&b| b == 0)?;
            let text = &rest[translated_end + 1..];
            (flag == 0).then_some(text)
        }
    };
    Some(TextChunk {
        offset: chunk.offset,
        kind,
        keyword,
        text,
        crc_ok: chunk.crc_ok,
    })
}

/// `png` with every `tEXt`, `iTXt` and `zTXt` chunk whose keyword is in `replace` removed, and
/// the given `tEXt` chunks inserted before the first `IDAT` (or before `IEND`). Keywords and
/// text must be Latin-1; callers Base64 anything else.
pub fn with_text_chunks(
    png: &[u8],
    replace: &[&str],
    add: &[(&str, &str)],
) -> Result<Vec<u8>, PngError> {
    let (all, _) = chunks(png)?;
    let mut out = SIGNATURE.to_vec();
    let mut inserted = false;
    for chunk in &all {
        if !inserted && (&chunk.kind == b"IDAT" || &chunk.kind == b"IEND") {
            for (keyword, text) in add {
                let mut data = Vec::with_capacity(keyword.len() + 1 + text.len());
                data.extend_from_slice(keyword.as_bytes());
                data.push(0);
                data.extend_from_slice(text.as_bytes());
                write_chunk(&mut out, *b"tEXt", &data);
            }
            inserted = true;
        }
        if text_chunk(chunk).is_some_and(|t| replace.contains(&t.keyword.as_str())) {
            continue;
        }
        write_chunk(&mut out, chunk.kind, chunk.data);
    }
    Ok(out)
}

/// Appends a chunk with a correct CRC.
pub fn write_chunk(out: &mut Vec<u8>, kind: [u8; 4], data: &[u8]) {
    let length = u32::try_from(data.len()).expect("chunk under 4 GiB");
    out.extend_from_slice(&length.to_be_bytes());
    let start = out.len();
    out.extend_from_slice(&kind);
    out.extend_from_slice(data);
    let crc = crc32(&out[start..]);
    out.extend_from_slice(&crc.to_be_bytes());
}

/// CRC-32 as PNG uses it (ISO 3309, reflected, polynomial 0xEDB88320).
pub fn crc32(bytes: &[u8]) -> u32 {
    const TABLE: [u32; 256] = {
        let mut table = [0u32; 256];
        let mut n = 0;
        while n < 256 {
            let mut c = n as u32;
            let mut k = 0;
            while k < 8 {
                c = if c & 1 != 0 {
                    0xedb8_8320 ^ (c >> 1)
                } else {
                    c >> 1
                };
                k += 1;
            }
            table[n] = c;
            n += 1;
        }
        table
    };
    let mut crc = 0xffff_ffffu32;
    for &b in bytes {
        crc = TABLE[((crc ^ b as u32) & 0xff) as usize] ^ (crc >> 8);
    }
    crc ^ 0xffff_ffff
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A valid 1x1 greyscale PNG.
    pub(crate) fn tiny() -> Vec<u8> {
        let mut png = SIGNATURE.to_vec();
        write_chunk(&mut png, *b"IHDR", &[0, 0, 0, 1, 0, 0, 0, 1, 8, 0, 0, 0, 0]);
        write_chunk(
            &mut png,
            *b"IDAT",
            &[0x78, 0x9c, 0x63, 0x60, 0x00, 0x00, 0x00, 0x02, 0x00, 0x01],
        );
        write_chunk(&mut png, *b"IEND", &[]);
        png
    }

    #[test]
    fn crc_matches_the_png_specification() {
        // The IEND chunk's CRC is fixed by the specification.
        assert_eq!(crc32(b"IEND"), 0xae42_6082);
        assert_eq!(crc32(b"123456789"), 0xcbf4_3926);
    }

    #[test]
    fn reads_and_rewrites_text_chunks() {
        let png = with_text_chunks(&tiny(), &[], &[("chara", "abc"), ("other", "x")]).unwrap();
        let (texts, ending) = text_chunks(&png).unwrap();
        assert_eq!(ending, Ending::Iend);
        let found: Vec<_> = texts
            .iter()
            .map(|t| (t.keyword.as_str(), t.text.unwrap(), t.crc_ok))
            .collect();
        assert_eq!(
            found,
            [("chara", &b"abc"[..], true), ("other", &b"x"[..], true)]
        );

        let replaced = with_text_chunks(&png, &["chara"], &[("chara", "def")]).unwrap();
        let (texts, _) = text_chunks(&replaced).unwrap();
        let keywords: Vec<_> = texts
            .iter()
            .map(|t| (t.keyword.as_str(), t.text.unwrap()))
            .collect();
        // Added chunks go just before the image data, after the ones kept.
        assert_eq!(keywords, [("other", &b"x"[..]), ("chara", &b"def"[..])]);
    }

    #[test]
    fn itxt_is_read_only_when_uncompressed() {
        let mut png = SIGNATURE.to_vec();
        write_chunk(&mut png, *b"IHDR", &[0; 13]);
        write_chunk(&mut png, *b"iTXt", b"ccv3\0\0\0en\0\0hello");
        write_chunk(&mut png, *b"iTXt", b"ccv3\0\x01\0\0\0zz");
        write_chunk(&mut png, *b"zTXt", b"chara\0\0zz");
        write_chunk(&mut png, *b"IEND", &[]);
        let (texts, _) = text_chunks(&png).unwrap();
        let found: Vec<_> = texts.iter().map(|t| (t.kind, t.text)).collect();
        assert_eq!(
            found,
            [
                (TextKind::International, Some(&b"hello"[..])),
                (TextKind::International, None),
                (TextKind::Compressed, None)
            ]
        );
    }

    #[test]
    fn hostile_lengths_are_errors_not_hangs() {
        // The CharacterBinder case: a length with the top bit set read as a negative number
        // moved the cursor backwards forever.
        let mut png = tiny()[..33].to_vec();
        png.extend_from_slice(&0xffff_fff8u32.to_be_bytes());
        png.extend_from_slice(b"tEXt");
        png.extend_from_slice(&[0; 4]);
        assert_eq!(
            chunks(&png).unwrap_err(),
            PngError::ChunkTooLong {
                offset: 33,
                length: 0xffff_fff8
            }
        );

        let mut long = tiny()[..33].to_vec();
        long.extend_from_slice(&1000u32.to_be_bytes());
        long.extend_from_slice(b"tEXt");
        long.extend_from_slice(&[0; 20]);
        assert_eq!(
            chunks(&long).unwrap_err(),
            PngError::Truncated { offset: 33 }
        );

        assert_eq!(chunks(&SIGNATURE).unwrap(), (vec![], false));
        assert_eq!(chunks(b"GIF89a").unwrap_err(), PngError::NotPng);
        let mut no_header = SIGNATURE.to_vec();
        write_chunk(&mut no_header, *b"tEXt", b"a\0b");
        assert_eq!(chunks(&no_header).unwrap_err(), PngError::NoHeader);
    }

    #[test]
    fn a_bad_crc_is_reported_not_fatal() {
        let mut png = with_text_chunks(&tiny(), &[], &[("chara", "abc")]).unwrap();
        let (texts, _) = text_chunks(&png).unwrap();
        let crc_at = texts[0].offset + 8 + "chara\0abc".len();
        png[crc_at] ^= 1;
        let (texts, _) = text_chunks(&png).unwrap();
        assert!(!texts[0].crc_ok);
    }
}
