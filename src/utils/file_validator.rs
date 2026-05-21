use sha2::{Digest, Sha256};
use thiserror::Error;

#[derive(Debug, Error)]
pub enum FileValidationError {
    #[error("File too large: {size} bytes (max {max} bytes)")]
    FileTooLarge { size: usize, max: usize },
    #[error("Unsupported MIME type: {mime}")]
    UnsupportedMimeType { mime: String },
    #[error("Invalid file header for type: {mime}")]
    InvalidFileHeader { mime: String },
    #[error("File is empty")]
    EmptyFile,
}

/// Validate file size and MIME type
pub fn validate_file(
    data: &[u8],
    mime_type: &str,
    allowed_types: &[String],
    max_size: usize,
) -> Result<(), FileValidationError> {
    if data.is_empty() {
        return Err(FileValidationError::EmptyFile);
    }

    if data.len() > max_size {
        return Err(FileValidationError::FileTooLarge {
            size: data.len(),
            max: max_size,
        });
    }

    let normalized = normalize_mime(mime_type);
    if !allowed_types.iter().any(|t| normalize_mime(t) == normalized) {
        return Err(FileValidationError::UnsupportedMimeType {
            mime: mime_type.to_string(),
        });
    }

    validate_file_header(data, &normalized)?;

    Ok(())
}

fn normalize_mime(mime: &str) -> String {
    mime.split(';').next().unwrap_or(mime).trim().to_lowercase()
}

/// Magic-byte validation for audio formats
fn validate_file_header(data: &[u8], mime: &str) -> Result<(), FileValidationError> {
    let valid = match mime {
        "audio/mpeg" => is_mp3(data),
        "audio/wav" => is_wav(data),
        "audio/ogg" => is_ogg(data),
        "audio/mp4" | "audio/x-m4a" => is_m4a(data),
        "audio/flac" => is_flac(data),
        _ => true, // unknown type, skip header check
    };

    if !valid {
        return Err(FileValidationError::InvalidFileHeader {
            mime: mime.to_string(),
        });
    }

    Ok(())
}

fn is_mp3(data: &[u8]) -> bool {
    if data.len() < 3 {
        return false;
    }
    // ID3 tag or MPEG sync word
    (data[0] == 0x49 && data[1] == 0x44 && data[2] == 0x33)
        || (data[0] == 0xFF && (data[1] & 0xE0) == 0xE0)
}

fn is_wav(data: &[u8]) -> bool {
    data.len() >= 12
        && &data[0..4] == b"RIFF"
        && &data[8..12] == b"WAVE"
}

fn is_ogg(data: &[u8]) -> bool {
    data.len() >= 4 && &data[0..4] == b"OggS"
}

fn is_m4a(data: &[u8]) -> bool {
    if data.len() < 12 {
        return false;
    }
    // ftyp box at offset 4
    &data[4..8] == b"ftyp"
}

fn is_flac(data: &[u8]) -> bool {
    data.len() >= 4 && &data[0..4] == b"fLaC"
}

/// Compute SHA-256 hash of file bytes (for duplicate detection)
pub fn compute_hash(data: &[u8]) -> String {
    let mut hasher = Sha256::new();
    hasher.update(data);
    hex::encode(hasher.finalize())
}

/// Determine content-type from file extension fallback
pub fn mime_from_extension(filename: &str) -> &'static str {
    let ext = filename
        .rsplit('.')
        .next()
        .unwrap_or("")
        .to_lowercase();

    match ext.as_str() {
        "mp3" => "audio/mpeg",
        "wav" => "audio/wav",
        "ogg" => "audio/ogg",
        "m4a" => "audio/x-m4a",
        "flac" => "audio/flac",
        _ => "application/octet-stream",
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn allowed() -> Vec<String> {
        vec![
            "audio/mpeg".to_string(),
            "audio/wav".to_string(),
            "audio/ogg".to_string(),
            "audio/mp4".to_string(),
            "audio/x-m4a".to_string(),
        ]
    }

    #[test]
    fn test_reject_empty_file() {
        let result = validate_file(&[], "audio/mpeg", &allowed(), 1024);
        assert!(matches!(result, Err(FileValidationError::EmptyFile)));
    }

    #[test]
    fn test_reject_oversized_file() {
        let data = vec![0u8; 1025];
        let result = validate_file(&data, "audio/mpeg", &allowed(), 1024);
        assert!(matches!(result, Err(FileValidationError::FileTooLarge { .. })));
    }

    #[test]
    fn test_reject_wrong_mime() {
        let data = vec![0u8; 100];
        let result = validate_file(&data, "video/mp4", &allowed(), 1_000_000);
        assert!(matches!(result, Err(FileValidationError::UnsupportedMimeType { .. })));
    }

    #[test]
    fn test_wav_magic_bytes() {
        let mut data = vec![0u8; 200];
        data[0..4].copy_from_slice(b"RIFF");
        data[8..12].copy_from_slice(b"WAVE");
        let result = validate_file(&data, "audio/wav", &allowed(), 1_000_000);
        assert!(result.is_ok());
    }

    #[test]
    fn test_ogg_magic_bytes() {
        let mut data = vec![0u8; 200];
        data[0..4].copy_from_slice(b"OggS");
        let result = validate_file(&data, "audio/ogg", &allowed(), 1_000_000);
        assert!(result.is_ok());
    }

    #[test]
    fn test_hash_consistency() {
        let data = b"test audio data";
        let h1 = compute_hash(data);
        let h2 = compute_hash(data);
        assert_eq!(h1, h2);
        assert_eq!(h1.len(), 64); // SHA-256 hex
    }

    #[test]
    fn test_hash_differs_for_different_input() {
        assert_ne!(compute_hash(b"alpha"), compute_hash(b"beta"));
    }

    #[test]
    fn test_mp3_id3_header_accepted() {
        let mut data = vec![0u8; 200];
        data[0..3].copy_from_slice(b"ID3");
        assert!(validate_file(&data, "audio/mpeg", &allowed(), 1_000_000).is_ok());
    }

    #[test]
    fn test_mp3_sync_word_accepted() {
        let mut data = vec![0u8; 200];
        data[0] = 0xFF;
        data[1] = 0xE0;
        assert!(validate_file(&data, "audio/mpeg", &allowed(), 1_000_000).is_ok());
    }

    #[test]
    fn test_mp3_garbage_rejected() {
        let data = vec![0xAA, 0xBB, 0xCC, 0xDD, 0xEE];
        let result = validate_file(&data, "audio/mpeg", &allowed(), 1_000_000);
        assert!(matches!(result, Err(FileValidationError::InvalidFileHeader { .. })));
    }

    #[test]
    fn test_flac_magic_bytes() {
        let mut data = vec![0u8; 200];
        data[0..4].copy_from_slice(b"fLaC");
        let mut allowed = allowed();
        allowed.push("audio/flac".to_string());
        assert!(validate_file(&data, "audio/flac", &allowed, 1_000_000).is_ok());
    }

    #[test]
    fn test_m4a_ftyp_box() {
        let mut data = vec![0u8; 200];
        data[4..8].copy_from_slice(b"ftyp");
        assert!(validate_file(&data, "audio/x-m4a", &allowed(), 1_000_000).is_ok());
    }

    #[test]
    fn test_mime_from_extension() {
        assert_eq!(mime_from_extension("song.mp3"), "audio/mpeg");
        assert_eq!(mime_from_extension("track.WAV"), "audio/wav");
        assert_eq!(mime_from_extension("a.ogg"), "audio/ogg");
        assert_eq!(mime_from_extension("b.m4a"), "audio/x-m4a");
        assert_eq!(mime_from_extension("c.flac"), "audio/flac");
        assert_eq!(mime_from_extension("readme"), "application/octet-stream");
        assert_eq!(mime_from_extension(""), "application/octet-stream");
    }

    #[test]
    fn test_mime_with_charset_param_normalized() {
        // multipart sometimes adds charset to MIME — ensure we strip it
        let mut data = vec![0u8; 200];
        data[0..4].copy_from_slice(b"RIFF");
        data[8..12].copy_from_slice(b"WAVE");
        assert!(validate_file(&data, "audio/wav; charset=binary", &allowed(), 1_000_000).is_ok());
    }
}
