//! A1 C5 (SPEC-A1 v5.2 §2.2): `worker_export_policy`, the one sensitive-name
//! list shared by `subagent_collect` and `subagent_integrate`. A withheld path
//! is listed by name only: its bytes never enter the diff, `diff_sha256` or an
//! integrate write. Symlinks are withheld by the callers (they need `lstat`).
use crate::tools::workspace::DEFAULT_EXCLUDED_NAMES;

const SSH_KEYS: &[&str] = &["id_rsa", "id_dsa", "id_ecdsa", "id_ed25519"];
const SENSITIVE_NAMES: &[&str] = &[
    ".envrc",
    ".npmrc",
    ".pypirc",
    ".netrc",
    "_netrc",
    ".git-credentials",
    ".htpasswd",
    "kubeconfig",
    "credentials.json",
    ".dockercfg",
];
const ENV_TEMPLATES: &[&str] = &[".env.example", ".env.sample", ".env.template"];
const SENSITIVE_EXTS: &[&str] = &["pem", "key", "p12", "pfx", "jks", "keystore", "kdbx"];
const SENSITIVE_DIRS: &[&str] = &[".ssh", ".gnupg", ".aws", ".kube", ".docker"];

fn sensitive_name(segment: &str) -> bool {
    let name = segment.to_ascii_lowercase();
    if SSH_KEYS.iter().any(|key| name.starts_with(key)) && !name.ends_with(".pub") {
        return true;
    }
    if name == ".env" || (name.starts_with(".env.") && !ENV_TEMPLATES.contains(&name.as_str())) {
        return true;
    }
    SENSITIVE_NAMES.contains(&name.as_str())
}

/// `None` when `path` (repository-relative, `/`-separated) may leave the worker;
/// otherwise the §2.2 reason: `protected`, `sensitive_name`, `sensitive_ext`,
/// `sensitive_dir` or `excluded_dir`.
pub(crate) fn worker_export_policy(path: &str) -> Option<&'static str> {
    let segments: Vec<&str> = path.split('/').filter(|s| !s.is_empty()).collect();
    let first = segments.first()?.to_ascii_lowercase();
    if first == ".git" || first == ".github" {
        return Some("protected");
    }
    let (file, dirs) = segments.split_last()?;
    if dirs
        .iter()
        .any(|d| SENSITIVE_DIRS.contains(&d.to_ascii_lowercase().as_str()))
    {
        return Some("sensitive_dir");
    }
    if segments.iter().any(|s| sensitive_name(s)) {
        return Some("sensitive_name");
    }
    if let Some((_, ext)) = file.rsplit_once('.') {
        if SENSITIVE_EXTS.contains(&ext.to_ascii_lowercase().as_str()) {
            return Some("sensitive_ext");
        }
    }
    if dirs.iter().any(|d| DEFAULT_EXCLUDED_NAMES.contains(d)) {
        return Some("excluded_dir");
    }
    None
}

#[cfg(test)]
mod tests {
    use super::worker_export_policy;

    #[test]
    fn export_policy_matches_the_spec_lists_item_by_item() {
        let withheld = [
            (".env", "sensitive_name"),
            (".env.local", "sensitive_name"),
            ("config/.env.production", "sensitive_name"),
            ("id_rsa", "sensitive_name"),
            ("keys/id_ed25519", "sensitive_name"),
            ("server.pem", "sensitive_ext"),
            ("tls/server.key", "sensitive_ext"),
            (".npmrc", "sensitive_name"),
            (".netrc", "sensitive_name"),
            (".git-credentials", "sensitive_name"),
            ("cert.p12", "sensitive_ext"),
            ("cert.pfx", "sensitive_ext"),
            ("kubeconfig", "sensitive_name"),
            (".envrc", "sensitive_name"),
            ("id_rsa_old", "sensitive_name"),
            ("keys/id_ed25519-work", "sensitive_name"),
            (".ssh/config", "sensitive_dir"),
            (".github/workflows/x.yml", "protected"),
            ("node_modules/x/index.js", "excluded_dir"),
            ("target/debug/x", "excluded_dir"),
        ];
        for (path, reason) in withheld {
            assert_eq!(worker_export_policy(path), Some(reason), "{path}");
        }
        for path in [
            ".gitignore",
            ".eslintrc.json",
            ".editorconfig",
            ".env.example",
            "id_rsa.pub",
            "id_ed25519_work.pub",
            "src/key_manager.rs",
            "docs/keys.md",
        ] {
            assert_eq!(worker_export_policy(path), None, "{path}");
        }
    }

    #[test]
    fn export_policy_is_case_insensitive_and_covers_every_segment() {
        for path in [
            ".GIT/config",
            "a/ID_RSA",
            "deep/.Env.Local",
            "x/.AWS/credentials",
            "y/Cert.PEM",
            "a/.gnupg/pubring.kbx",
            "pkg/credentials.json",
            "a/.env/inner.txt",
        ] {
            assert!(worker_export_policy(path).is_some(), "{path}");
        }
        for path in [".env.sample", ".env.template", "src/keys.rs", "a/.nvmrc"] {
            assert_eq!(worker_export_policy(path), None, "{path}");
        }
    }
}
