/// Утилиты для обработки ZIP-архивов (п. 1.7 ТЗ).
/// Извлекает аудиофайлы из ZIP и возвращает список (имя, байты).
 
use std::io::{Cursor, Read};
use thiserror::Error;
use zip::ZipArchive;
 
use crate::utils::file_validator::mime_from_extension;
 
#[derive(Debug, Error)]
pub enum ZipError {
    #[error("Failed to open ZIP archive: {0}")]
    InvalidZip(#[from] zip::result::ZipError),
    #[error("ZIP archive is empty or contains no supported audio files")]
    NoAudioFiles,
    #[error("Failed to read entry: {0}")]
    ReadError(#[from] std::io::Error),
}
 
/// Файл, извлечённый из ZIP-архива.
pub struct ExtractedFile {
    pub name: String,
    pub data: Vec<u8>,
    pub mime_type: String,
}
 
/// Допустимые аудио-расширения (те же, что проверяет `file_validator`).
const AUDIO_EXTENSIONS: &[&str] = &["mp3", "wav", "ogg", "m4a", "flac"];
 
/// Извлекает все поддерживаемые аудиофайлы из ZIP-байтов.
/// Возвращает `ZipError::NoAudioFiles`, если ни одного не нашлось.
pub fn extract_audio_from_zip(zip_bytes: &[u8]) -> Result<Vec<ExtractedFile>, ZipError> {
    let cursor = Cursor::new(zip_bytes);
    let mut archive = ZipArchive::new(cursor)?;
 
    let mut files = Vec::new();
 
    for i in 0..archive.len() {
        let mut entry = archive.by_index(i)?;
 
        // Пропускаем директории
        if entry.is_dir() {
            continue;
        }
 
        let raw_name = entry.name().to_string();
        // Берём только имя файла без пути
        let file_name = raw_name
            .rsplit('/')
            .next()
            .unwrap_or(&raw_name)
            .to_string();
 
        let ext = file_name
            .rsplit('.')
            .next()
            .unwrap_or("")
            .to_lowercase();
 
        if !AUDIO_EXTENSIONS.contains(&ext.as_str()) {
            continue;
        }
 
        let mut data = Vec::new();
        entry.read_to_end(&mut data)?;
 
        let mime_type = mime_from_extension(&file_name).to_string();
 
        files.push(ExtractedFile {
            name: file_name,
            data,
            mime_type,
        });
    }
 
    if files.is_empty() {
        return Err(ZipError::NoAudioFiles);
    }
 
    Ok(files)
}
 
#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;
    use zip::write::FileOptions;
 
    fn make_zip_with(entries: &[(&str, &[u8])]) -> Vec<u8> {
        let buf = Vec::new();
        let cursor = Cursor::new(buf);
        let mut zip = zip::ZipWriter::new(cursor);
        let opts = FileOptions::default();
        for (name, data) in entries {
            zip.start_file(*name, opts).unwrap();
            zip.write_all(data).unwrap();
        }
        zip.finish().unwrap().into_inner()
    }
 
    #[test]
    fn test_extracts_mp3_from_zip() {
        // Минимальные MP3-байты (ID3 header)
        let mp3_bytes = b"\x49\x44\x33\x00\x00\x00\x00\x00\x00\x00";
        let zip_bytes = make_zip_with(&[("track.mp3", mp3_bytes)]);
 
        let result = extract_audio_from_zip(&zip_bytes).unwrap();
        assert_eq!(result.len(), 1);
        assert_eq!(result[0].name, "track.mp3");
        assert_eq!(result[0].mime_type, "audio/mpeg");
    }
 
    #[test]
    fn test_skips_non_audio_files() {
        let zip_bytes = make_zip_with(&[
            ("readme.txt", b"hello"),
            ("cover.jpg", b"\xFF\xD8\xFF"),
        ]);
        let result = extract_audio_from_zip(&zip_bytes);
        assert!(matches!(result, Err(ZipError::NoAudioFiles)));
    }
 
    #[test]
    fn test_extracts_multiple_audio_files() {
        let wav_bytes = b"RIFF\x00\x00\x00\x00WAVEfmt ";
        let ogg_bytes = b"OggS\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00";
        let zip_bytes = make_zip_with(&[
            ("a.wav", wav_bytes),
            ("b.ogg", ogg_bytes),
            ("notes.txt", b"ignore"),
        ]);
 
        let result = extract_audio_from_zip(&zip_bytes).unwrap();
        assert_eq!(result.len(), 2);
    }
 
    #[test]
    fn test_extracts_file_name_from_path() {
        let mp3_bytes = b"\x49\x44\x33\x00\x00\x00\x00\x00\x00\x00";
        let zip_bytes = make_zip_with(&[("folder/sub/track.mp3", mp3_bytes)]);
 
        let result = extract_audio_from_zip(&zip_bytes).unwrap();
        assert_eq!(result[0].name, "track.mp3");
    }
 
    #[test]
    fn test_invalid_zip_returns_error() {
        let result = extract_audio_from_zip(b"this is not a zip");
        assert!(result.is_err());
    }
}