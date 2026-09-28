use crate::{ToolCall, VerifiedInvocation};
use sha2::{Digest, Sha256};
use std::{
    collections::{BTreeMap, BTreeSet},
    error::Error,
    fmt,
};

pub const MAX_ARGC: usize = 128;
pub const MAX_TOKEN_BYTES: usize = 4 * 1024;
pub const MAX_COMMAND_BYTES: usize = 64 * 1024;
pub const MAX_RULES: usize = 512;
pub const MAX_PATTERN_TOKENS: usize = 32;
pub const MAX_ALTERNATIVES: usize = 32;
pub const MAX_EXAMPLES_PER_RULE: usize = 64;
pub const MAX_JUSTIFICATION_BYTES: usize = 512;

#[derive(Clone, Copy, Debug, Eq, Ord, PartialEq, PartialOrd)]
pub enum ExecDecision {
    Allow,
    Prompt,
    Forbidden,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum PolicyErrorKind {
    InvalidCommand,
    InvalidRule,
    InvalidExample,
    InvalidHostExecutable,
    InvalidApproval,
}

#[derive(Clone)]
pub struct PolicyError {
    pub kind: PolicyErrorKind,
    message: &'static str,
}

impl PolicyError {
    const fn new(kind: PolicyErrorKind, message: &'static str) -> Self {
        Self { kind, message }
    }

    pub fn public_message(&self) -> &'static str {
        self.message
    }
}

impl fmt::Debug for PolicyError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("PolicyError")
            .field("kind", &self.kind)
            .field("message", &self.message)
            .finish()
    }
}

impl fmt::Display for PolicyError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.message)
    }
}

impl Error for PolicyError {}

#[derive(Clone, Eq, PartialEq)]
pub struct Command {
    argv: Vec<String>,
}

impl Command {
    pub fn new(argv: Vec<String>) -> Result<Self, PolicyError> {
        if argv.is_empty() || argv.len() > MAX_ARGC {
            return Err(PolicyError::new(
                PolicyErrorKind::InvalidCommand,
                "invalid command argument count",
            ));
        }

        let mut total = 0usize;
        for (index, token) in argv.iter().enumerate() {
            if token.len() > MAX_TOKEN_BYTES
                || token.chars().any(char::is_control)
                || (index == 0 && token.is_empty())
            {
                return Err(PolicyError::new(
                    PolicyErrorKind::InvalidCommand,
                    "invalid command token",
                ));
            }
            total = total.checked_add(token.len()).ok_or_else(|| {
                PolicyError::new(PolicyErrorKind::InvalidCommand, "command size overflow")
            })?;
        }
        if total > MAX_COMMAND_BYTES {
            return Err(PolicyError::new(
                PolicyErrorKind::InvalidCommand,
                "command is too large",
            ));
        }
        Ok(Self { argv })
    }

    pub fn argv(&self) -> &[String] {
        &self.argv
    }

    pub fn fingerprint(&self) -> CommandFingerprint {
        let mut digest = Sha256::new();
        digest.update(b"coding-tools-command-v1\0");
        for token in &self.argv {
            digest.update((token.len() as u64).to_be_bytes());
            digest.update(token.as_bytes());
        }
        CommandFingerprint(digest.finalize().into())
    }
}

impl fmt::Debug for Command {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("Command")
            .field("argc", &self.argv.len())
            .field("argv", &"<redacted>")
            .finish()
    }
}

#[derive(Clone, Eq, PartialEq)]
pub struct CommandFingerprint([u8; 32]);

impl fmt::Debug for CommandFingerprint {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str("CommandFingerprint(<redacted>)")
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum TokenPattern {
    Exact(String),
    OneOf(BTreeSet<String>),
}

impl TokenPattern {
    pub fn exact(value: impl Into<String>) -> Result<Self, PolicyError> {
        let value = value.into();
        validate_pattern_token(&value)?;
        Ok(Self::Exact(value))
    }

    pub fn one_of(values: impl IntoIterator<Item = String>) -> Result<Self, PolicyError> {
        let values: BTreeSet<_> = values.into_iter().collect();
        if values.is_empty() || values.len() > MAX_ALTERNATIVES {
            return Err(PolicyError::new(
                PolicyErrorKind::InvalidRule,
                "invalid token alternatives",
            ));
        }
        for value in &values {
            validate_pattern_token(value)?;
        }
        Ok(Self::OneOf(values))
    }

    fn matches(&self, value: &str) -> bool {
        match self {
            Self::Exact(expected) => expected == value,
            Self::OneOf(expected) => expected.contains(value),
        }
    }
}

fn validate_pattern_token(value: &str) -> Result<(), PolicyError> {
    if value.is_empty() || value.len() > MAX_TOKEN_BYTES || value.chars().any(char::is_control) {
        return Err(PolicyError::new(
            PolicyErrorKind::InvalidRule,
            "invalid policy token",
        ));
    }
    Ok(())
}

#[derive(Clone, Debug)]
pub struct PrefixRule {
    pattern: Vec<TokenPattern>,
    decision: ExecDecision,
    justification: Option<String>,
    must_match: Vec<Vec<String>>,
    must_not_match: Vec<Vec<String>>,
}

impl PrefixRule {
    pub fn new(pattern: Vec<TokenPattern>, decision: ExecDecision) -> Result<Self, PolicyError> {
        if pattern.is_empty() || pattern.len() > MAX_PATTERN_TOKENS {
            return Err(PolicyError::new(
                PolicyErrorKind::InvalidRule,
                "invalid rule pattern length",
            ));
        }
        Ok(Self {
            pattern,
            decision,
            justification: None,
            must_match: Vec::new(),
            must_not_match: Vec::new(),
        })
    }

    pub fn justification(mut self, value: impl Into<String>) -> Result<Self, PolicyError> {
        let value = value.into();
        if value.is_empty()
            || value.len() > MAX_JUSTIFICATION_BYTES
            || value.chars().any(char::is_control)
        {
            return Err(PolicyError::new(
                PolicyErrorKind::InvalidRule,
                "invalid rule justification",
            ));
        }
        self.justification = Some(value);
        Ok(self)
    }

    pub fn examples(
        mut self,
        must_match: Vec<Vec<String>>,
        must_not_match: Vec<Vec<String>>,
    ) -> Result<Self, PolicyError> {
        if must_match.len() > MAX_EXAMPLES_PER_RULE || must_not_match.len() > MAX_EXAMPLES_PER_RULE
        {
            return Err(PolicyError::new(
                PolicyErrorKind::InvalidExample,
                "too many rule examples",
            ));
        }
        self.must_match = must_match;
        self.must_not_match = must_not_match;
        self.validate_examples()?;
        Ok(self)
    }

    fn validate_examples(&self) -> Result<(), PolicyError> {
        for argv in &self.must_match {
            let command = Command::new(argv.clone()).map_err(|_| {
                PolicyError::new(
                    PolicyErrorKind::InvalidExample,
                    "invalid positive rule example",
                )
            })?;
            if !self.matches(command.argv()) {
                return Err(PolicyError::new(
                    PolicyErrorKind::InvalidExample,
                    "positive rule example does not match",
                ));
            }
        }
        for argv in &self.must_not_match {
            let command = Command::new(argv.clone()).map_err(|_| {
                PolicyError::new(
                    PolicyErrorKind::InvalidExample,
                    "invalid negative rule example",
                )
            })?;
            if self.matches(command.argv()) {
                return Err(PolicyError::new(
                    PolicyErrorKind::InvalidExample,
                    "negative rule example unexpectedly matches",
                ));
            }
        }
        Ok(())
    }

    fn matches(&self, argv: &[String]) -> bool {
        self.pattern.len() <= argv.len()
            && self
                .pattern
                .iter()
                .zip(argv)
                .all(|(pattern, value)| pattern.matches(value))
    }
}

#[derive(Clone, Debug)]
pub struct HostExecutable {
    name: String,
    paths: BTreeSet<String>,
}

impl HostExecutable {
    pub fn new(
        name: impl Into<String>,
        paths: impl IntoIterator<Item = String>,
    ) -> Result<Self, PolicyError> {
        let name = name.into();
        if name.is_empty()
            || name.len() > MAX_TOKEN_BYTES
            || name.chars().any(char::is_control)
            || name.contains('/')
            || name.contains('\\')
        {
            return Err(PolicyError::new(
                PolicyErrorKind::InvalidHostExecutable,
                "invalid host executable name",
            ));
        }
        let paths: BTreeSet<_> = paths.into_iter().collect();
        if paths.is_empty() || paths.len() > MAX_ALTERNATIVES {
            return Err(PolicyError::new(
                PolicyErrorKind::InvalidHostExecutable,
                "invalid host executable paths",
            ));
        }
        for path in &paths {
            if path.len() > MAX_TOKEN_BYTES
                || path.chars().any(char::is_control)
                || !is_absolute_program(path)
                || lexical_basename(path) != Some(name.as_str())
            {
                return Err(PolicyError::new(
                    PolicyErrorKind::InvalidHostExecutable,
                    "invalid host executable path",
                ));
            }
        }
        Ok(Self { name, paths })
    }
}

#[derive(Clone, Debug)]
pub struct PrefixRuleMatch {
    pub decision: ExecDecision,
    pub matched_prefix: Vec<String>,
    pub justification: Option<String>,
    pub resolved_program: Option<String>,
}

#[derive(Clone, Debug, Default)]
pub struct PolicyEvaluation {
    pub matched_rules: Vec<PrefixRuleMatch>,
    pub decision: Option<ExecDecision>,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ExecutionAuthorization {
    Allowed,
    ApprovalRequired,
    Forbidden,
    NoMatchingRule,
}

#[derive(Clone, Debug)]
pub struct ExecPolicy {
    rules: Vec<PrefixRule>,
    host_executables: BTreeMap<String, BTreeSet<String>>,
    resolve_host_executables: bool,
}

impl ExecPolicy {
    pub fn new(
        rules: Vec<PrefixRule>,
        host_executables: Vec<HostExecutable>,
        resolve_host_executables: bool,
    ) -> Result<Self, PolicyError> {
        if rules.len() > MAX_RULES {
            return Err(PolicyError::new(
                PolicyErrorKind::InvalidRule,
                "too many execution policy rules",
            ));
        }
        for rule in &rules {
            rule.validate_examples()?;
        }
        let mut hosts = BTreeMap::new();
        for host in host_executables {
            if hosts.insert(host.name, host.paths).is_some() {
                return Err(PolicyError::new(
                    PolicyErrorKind::InvalidHostExecutable,
                    "duplicate host executable",
                ));
            }
        }
        Ok(Self {
            rules,
            host_executables: hosts,
            resolve_host_executables,
        })
    }

    pub fn evaluate(&self, command: &Command) -> PolicyEvaluation {
        let exact = self.collect_matches(command.argv(), None);
        if !exact.matched_rules.is_empty() || !self.resolve_host_executables {
            return exact;
        }

        let program = &command.argv()[0];
        if !is_absolute_program(program) {
            return exact;
        }
        let Some(base) = lexical_basename(program) else {
            return exact;
        };
        if let Some(allowed) = self.host_executables.get(base) {
            if !allowed.contains(program) {
                return exact;
            }
        }

        let mut resolved = command.argv().to_vec();
        resolved[0] = base.to_owned();
        self.collect_matches(&resolved, Some(program.as_str()))
    }

    pub fn authorize(
        &self,
        command: &Command,
        call: &ToolCall,
        verified: &VerifiedInvocation<'_>,
        approval: Option<&ScopedApproval>,
        now_unix_ms: u64,
    ) -> ExecutionAuthorization {
        match self.evaluate(command).decision {
            None => ExecutionAuthorization::NoMatchingRule,
            Some(ExecDecision::Forbidden) => ExecutionAuthorization::Forbidden,
            Some(ExecDecision::Allow) => ExecutionAuthorization::Allowed,
            Some(ExecDecision::Prompt) => {
                if approval
                    .is_some_and(|approval| approval.matches(command, call, verified, now_unix_ms))
                {
                    ExecutionAuthorization::Allowed
                } else {
                    ExecutionAuthorization::ApprovalRequired
                }
            }
        }
    }

    fn collect_matches(&self, argv: &[String], resolved_program: Option<&str>) -> PolicyEvaluation {
        let mut matched_rules = Vec::new();
        let mut decision: Option<ExecDecision> = None;
        for rule in &self.rules {
            if !rule.matches(argv) {
                continue;
            }
            let candidate = rule.decision;
            decision = Some(decision.map_or(candidate, |current| current.max(candidate)));
            matched_rules.push(PrefixRuleMatch {
                decision: candidate,
                matched_prefix: argv[..rule.pattern.len()].to_vec(),
                justification: rule.justification.clone(),
                resolved_program: resolved_program.map(str::to_owned),
            });
        }
        PolicyEvaluation {
            matched_rules,
            decision,
        }
    }
}

#[derive(Clone, Eq, PartialEq)]
pub struct ScopedApproval {
    command: CommandFingerprint,
    context: [u8; 32],
    generation: u64,
    expires_at_unix_ms: u64,
}

impl ScopedApproval {
    #[cfg(test)]
    fn issue_local(
        command: &Command,
        call: &ToolCall,
        verified: &VerifiedInvocation<'_>,
        expires_at_unix_ms: u64,
    ) -> Result<Self, PolicyError> {
        if expires_at_unix_ms == 0 || expires_at_unix_ms > verified.expires_at_unix_ms() {
            return Err(PolicyError::new(
                PolicyErrorKind::InvalidApproval,
                "invalid approval expiry",
            ));
        }
        Ok(Self {
            command: command.fingerprint(),
            context: approval_context(call, verified.generation()),
            generation: verified.generation(),
            expires_at_unix_ms,
        })
    }

    fn matches(
        &self,
        command: &Command,
        call: &ToolCall,
        verified: &VerifiedInvocation<'_>,
        now_unix_ms: u64,
    ) -> bool {
        now_unix_ms <= self.expires_at_unix_ms
            && self.expires_at_unix_ms <= verified.expires_at_unix_ms()
            && self.generation == verified.generation()
            && self.command == command.fingerprint()
            && self.context == approval_context(call, verified.generation())
    }
}

impl fmt::Debug for ScopedApproval {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("ScopedApproval")
            .field("command", &"<redacted>")
            .field("context", &"<opaque>")
            .field("generation", &self.generation)
            .field("expires_at_unix_ms", &self.expires_at_unix_ms)
            .finish()
    }
}

fn approval_context(call: &ToolCall, generation: u64) -> [u8; 32] {
    let mut digest = Sha256::new();
    digest.update(b"coding-tools-scoped-approval-v1\0");
    for value in [
        call.request_id.as_str(),
        call.conversation_id.as_str(),
        call.workspace_id.as_str(),
        call.tool_name.as_str(),
    ] {
        digest.update((value.len() as u64).to_be_bytes());
        digest.update(value.as_bytes());
    }
    digest.update(generation.to_be_bytes());
    digest.finalize().into()
}

fn is_absolute_program(value: &str) -> bool {
    let bytes = value.as_bytes();
    value.starts_with('/')
        || value.starts_with("\\\\")
        || value.starts_with("//")
        || (bytes.len() >= 3
            && bytes[0].is_ascii_alphabetic()
            && bytes[1] == b':'
            && matches!(bytes[2], b'/' | b'\\'))
}

fn lexical_basename(value: &str) -> Option<&str> {
    value
        .rsplit(['/', '\\'])
        .find(|part| !part.is_empty())
        .filter(|part| !part.contains(':'))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{Capability, LocalAdmission, ToolName};
    use serde_json::json;

    fn command(parts: &[&str]) -> Command {
        Command::new(parts.iter().map(|v| (*v).to_owned()).collect()).unwrap()
    }

    fn exact(parts: &[&str], decision: ExecDecision) -> PrefixRule {
        PrefixRule::new(
            parts
                .iter()
                .map(|v| TokenPattern::exact(*v).unwrap())
                .collect(),
            decision,
        )
        .unwrap()
    }

    fn call(request: &str) -> ToolCall {
        ToolCall::new(
            request,
            "conversation-a",
            "workspace-a",
            ToolName::parse("exec_command").unwrap(),
            json!({}),
        )
        .unwrap()
    }

    fn admission() -> LocalAdmission {
        LocalAdmission::fixture(
            "conversation-a",
            "workspace-a",
            [Capability::ProcessExec],
            9,
            5_000,
        )
    }

    #[test]
    fn command_bounds_reject_invalid_input() {
        assert_eq!(
            Command::new(vec![]).unwrap_err().kind,
            PolicyErrorKind::InvalidCommand
        );
        assert!(Command::new(vec!["git\nstatus".into()]).is_err());
        assert!(Command::new(vec!["x".repeat(MAX_TOKEN_BYTES + 1)]).is_err());
        assert!(Command::new(vec!["git".into(); MAX_ARGC + 1]).is_err());
    }

    #[test]
    fn alternatives_and_prefix_matching_are_deterministic() {
        let rule = PrefixRule::new(
            vec![
                TokenPattern::exact("git").unwrap(),
                TokenPattern::one_of(["status".to_owned(), "diff".to_owned()]).unwrap(),
            ],
            ExecDecision::Allow,
        )
        .unwrap();
        let policy = ExecPolicy::new(vec![rule], vec![], false).unwrap();
        assert_eq!(
            policy
                .evaluate(&command(&["git", "status", "--short"]))
                .decision,
            Some(ExecDecision::Allow)
        );
        assert_eq!(policy.evaluate(&command(&["git", "push"])).decision, None);
    }

    #[test]
    fn strictest_matching_decision_wins() {
        let policy = ExecPolicy::new(
            vec![
                exact(&["git"], ExecDecision::Allow),
                exact(&["git", "push"], ExecDecision::Prompt),
                exact(&["git", "push", "--force"], ExecDecision::Forbidden),
            ],
            vec![],
            false,
        )
        .unwrap();
        assert_eq!(
            policy
                .evaluate(&command(&["git", "push", "--force"]))
                .decision,
            Some(ExecDecision::Forbidden)
        );
        assert_eq!(
            policy.evaluate(&command(&["git", "push"])).decision,
            Some(ExecDecision::Prompt)
        );
    }

    #[test]
    fn no_match_is_explicit_not_allow() {
        let policy =
            ExecPolicy::new(vec![exact(&["git"], ExecDecision::Allow)], vec![], false).unwrap();
        let c = command(&["python", "script.py"]);
        assert_eq!(policy.evaluate(&c).decision, None);
        let local = admission();
        let verified = VerifiedInvocation::fixture(&local);
        assert_eq!(
            policy.authorize(&c, &call("request-a"), &verified, None, 100),
            ExecutionAuthorization::NoMatchingRule
        );
    }

    #[test]
    fn examples_are_policy_load_tests() {
        let good = exact(&["git", "status"], ExecDecision::Allow)
            .examples(
                vec![vec!["git".into(), "status".into(), "--short".into()]],
                vec![vec!["git".into(), "push".into()]],
            )
            .unwrap();
        assert!(ExecPolicy::new(vec![good], vec![], false).is_ok());

        assert!(exact(&["git", "status"], ExecDecision::Allow)
            .examples(vec![vec!["git".into(), "push".into()]], vec![])
            .is_err());
        assert!(exact(&["git"], ExecDecision::Allow)
            .examples(vec![], vec![vec!["git".into(), "status".into()]])
            .is_err());
    }

    #[test]
    fn exact_absolute_rule_precedes_basename_fallback() {
        let policy = ExecPolicy::new(
            vec![
                exact(&["git"], ExecDecision::Allow),
                exact(&["/usr/bin/git"], ExecDecision::Forbidden),
            ],
            vec![],
            true,
        )
        .unwrap();
        let result = policy.evaluate(&command(&["/usr/bin/git", "status"]));
        assert_eq!(result.decision, Some(ExecDecision::Forbidden));
        assert_eq!(result.matched_rules.len(), 1);
        assert_eq!(result.matched_rules[0].resolved_program, None);
    }

    #[test]
    fn host_executable_fallback_is_opt_in_and_path_constrained() {
        let rule = exact(&["git", "status"], ExecDecision::Allow);
        let disabled = ExecPolicy::new(vec![rule.clone()], vec![], false).unwrap();
        assert_eq!(
            disabled
                .evaluate(&command(&["/usr/bin/git", "status"]))
                .decision,
            None
        );

        let enabled = ExecPolicy::new(
            vec![rule],
            vec![HostExecutable::new("git", ["/usr/bin/git".to_owned()]).unwrap()],
            true,
        )
        .unwrap();
        let ok = enabled.evaluate(&command(&["/usr/bin/git", "status"]));
        assert_eq!(ok.decision, Some(ExecDecision::Allow));
        assert_eq!(
            ok.matched_rules[0].resolved_program.as_deref(),
            Some("/usr/bin/git")
        );
        assert_eq!(
            enabled
                .evaluate(&command(&["/opt/bin/git", "status"]))
                .decision,
            None
        );
    }

    #[test]
    fn windows_absolute_paths_use_same_lexical_rules_on_all_hosts() {
        let policy = ExecPolicy::new(
            vec![exact(&["git", "status"], ExecDecision::Prompt)],
            vec![HostExecutable::new("git", ["C:/Program Files/Git/cmd/git".to_owned()]).unwrap()],
            true,
        )
        .unwrap();
        let result = policy.evaluate(&command(&["C:/Program Files/Git/cmd/git", "status"]));
        assert_eq!(result.decision, Some(ExecDecision::Prompt));
    }

    #[test]
    fn prompt_requires_exact_scoped_approval() {
        let policy = ExecPolicy::new(
            vec![exact(&["git", "push"], ExecDecision::Prompt)],
            vec![],
            false,
        )
        .unwrap();
        let c = command(&["git", "push"]);
        let tc = call("request-a");
        let local = admission();
        let verified = VerifiedInvocation::fixture(&local);

        assert_eq!(
            policy.authorize(&c, &tc, &verified, None, 100),
            ExecutionAuthorization::ApprovalRequired
        );
        let approval = ScopedApproval::issue_local(&c, &tc, &verified, 1_000).unwrap();
        assert_eq!(
            policy.authorize(&c, &tc, &verified, Some(&approval), 100),
            ExecutionAuthorization::Allowed
        );
        assert_eq!(
            policy.authorize(
                &command(&["git", "push", "--force"]),
                &tc,
                &verified,
                Some(&approval),
                100,
            ),
            ExecutionAuthorization::ApprovalRequired
        );
        assert_eq!(
            policy.authorize(&c, &call("request-b"), &verified, Some(&approval), 100,),
            ExecutionAuthorization::ApprovalRequired
        );
        assert_eq!(
            policy.authorize(&c, &tc, &verified, Some(&approval), 1_001),
            ExecutionAuthorization::ApprovalRequired
        );
    }

    #[test]
    fn forbidden_cannot_be_overridden_by_approval() {
        let policy = ExecPolicy::new(
            vec![
                exact(&["git"], ExecDecision::Prompt),
                exact(&["git", "push", "--force"], ExecDecision::Forbidden),
            ],
            vec![],
            false,
        )
        .unwrap();
        let c = command(&["git", "push", "--force"]);
        let tc = call("request-a");
        let local = admission();
        let verified = VerifiedInvocation::fixture(&local);
        let approval = ScopedApproval::issue_local(&c, &tc, &verified, 1_000).unwrap();
        assert_eq!(
            policy.authorize(&c, &tc, &verified, Some(&approval), 100),
            ExecutionAuthorization::Forbidden
        );
    }

    #[test]
    fn approval_cannot_outlive_local_admission() {
        let c = command(&["cargo", "test"]);
        let tc = call("request-a");
        let local = admission();
        let verified = VerifiedInvocation::fixture(&local);
        assert_eq!(
            ScopedApproval::issue_local(&c, &tc, &verified, 5_001)
                .unwrap_err()
                .kind,
            PolicyErrorKind::InvalidApproval
        );
    }

    #[test]
    fn approval_debug_redacts_command_and_context() {
        let c = command(&["secret-program", "secret-argument"]);
        let tc = call("request-a");
        let local = admission();
        let verified = VerifiedInvocation::fixture(&local);
        let approval = ScopedApproval::issue_local(&c, &tc, &verified, 1_000).unwrap();
        let rendered = format!("{approval:?}");
        assert!(!rendered.contains("secret-program"));
        assert!(!rendered.contains("conversation-a"));
        assert!(!rendered.contains("workspace-a"));
    }
}
