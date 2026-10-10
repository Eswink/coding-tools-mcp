//! Narrow execution input names; this source is also tested unchanged on Linux.
pub(super) fn components(text: &str) -> Result<Vec<&str>, &'static str> {
    if text.is_empty() || text.len() > 4096 {
        return Err("WINDOWS_INPUT_PATH_REJECTED");
    }
    let parts: Vec<_> = text.split(['/', '\\']).collect();
    if parts.len() > 64 || parts.iter().any(|part| !component(part)) {
        return Err("WINDOWS_INPUT_PATH_REJECTED");
    }
    Ok(parts)
}
pub(super) fn component(text: &str) -> bool {
    if text.is_empty()
        || text == "."
        || text == ".."
        || text.encode_utf16().count() > 255
        || text.ends_with(['.', ' '])
        || text.chars().any(|c| {
            c.is_control() || matches!(c, ':' | '/' | '\\' | '<' | '>' | '"' | '|' | '?' | '*')
        })
    {
        return false;
    }
    let base = text
        .split('.')
        .next()
        .unwrap_or("")
        .trim_end_matches(' ')
        .to_ascii_uppercase();
    !matches!(
        base.as_str(),
        "CON" | "PRN" | "AUX" | "NUL" | "CLOCK$" | "CONIN$" | "CONOUT$"
    ) && !["COM", "LPT"].iter().any(|prefix| {
        base.strip_prefix(prefix).is_some_and(|n| {
            matches!(
                n,
                "1" | "2" | "3" | "4" | "5" | "6" | "7" | "8" | "9" | "¹" | "²" | "³"
            )
        })
    })
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn relative_nested_names_are_preserved_without_rewriting() {
        assert_eq!(
            components("src/配置\\a.rs").unwrap(),
            ["src", "配置", "a.rs"]
        );
        assert!(components("a b/c.d").is_ok());
    }
    #[test]
    fn escapes_streams_devices_and_ambiguous_names_are_denied() {
        for value in [
            "",
            "/a",
            "\\a",
            "a//b",
            "a\\\\b",
            ".",
            "..",
            "a/../b",
            "C:a",
            "C:\\a",
            "\\\\host\\a",
            "a:stream",
            "a.",
            "a ",
            "NUL.txt",
            "NUL .txt",
            "COM1 .log",
            "con",
            "com1.log",
            "Lpt9",
            "COM¹",
            "LPT².txt",
            "CONIN$",
            "CLOCK$",
            "a\0",
            "a\n",
            "a?b",
            "a*b",
            "a|b",
        ] {
            assert!(components(value).is_err(), "{value:?}");
        }
    }
    #[test]
    fn lengths_and_component_counts_are_bounded() {
        assert!(components(&"x".repeat(255)).is_ok());
        assert!(components(&"x".repeat(256)).is_err());
        assert!(components(&vec!["a"; 64].join("/")).is_ok());
        assert!(components(&vec!["a"; 65].join("/")).is_err());
        assert!(components(&"配置".repeat(128)).is_err());
    }
}
