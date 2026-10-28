//! Reconnect policy for the always-on live Agent (S1).
//! Pure classification and pacing only: no I/O, no wall clock, no authority.
use crate::AgentError;
use std::time::Duration;

/// What the supervisor may do after a session ends with an error.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RetryClass {
    /// Transient: back off and reconnect. Never replays work (the journal and
    /// the cloud admission ledger decide that, not this loop).
    Retryable,
    /// A person must act (re-import credentials, trust the CA, review the
    /// journal). Retrying cannot help and would only hammer the gateway.
    NeedsOperator,
    /// Internal invariant failure. Stop and surface it; never loop.
    Fatal,
}

/// Total over `AgentError`; deliberately no wildcard arm so a new variant must
/// be classified consciously.
pub fn classify_retry(error: AgentError) -> RetryClass {
    use AgentError::*;
    match error {
        Transport | LocalAuthority | Capacity | Protocol | ExecutionUnknown => {
            RetryClass::Retryable
        }
        Configuration | Credentials | Journal | Authentication | Tls => RetryClass::NeedsOperator,
        Arguments | Cancelled | Exhausted | Duplicate => RetryClass::Fatal,
    }
}

/// Base delay before reconnect attempt `attempt` (1-based): 1s, 2s, 4s .. 30s cap.
pub fn backoff_base(attempt: u32) -> Duration {
    Duration::from_secs((1u64 << attempt.saturating_sub(1).min(5)).min(30))
}
/// Base delay plus 0..=25% jitter. `jitter_permille` is clamped to 0..=1000.
pub fn backoff_delay(attempt: u32, jitter_permille: u64) -> Duration {
    let base = backoff_base(attempt);
    base + base * (jitter_permille.min(1000) as u32) / 4000
}
/// Injectable randomness so reconnect pacing is deterministic under test.
pub trait Jitter: Send + Sync + 'static {
    /// A value in 0..=1000.
    fn permille(&self) -> u64;
}
/// Production source: OS CSPRNG. Never needs to be secret, only decorrelated.
pub struct SystemJitter;
impl Jitter for SystemJitter {
    fn permille(&self) -> u64 {
        use ring::rand::SecureRandom;
        let mut b = [0u8; 2];
        if ring::rand::SystemRandom::new().fill(&mut b).is_err() {
            return 500;
        }
        u64::from(u16::from_le_bytes(b)) * 1000 / u64::from(u16::MAX)
    }
}

/// Observable connection state for the native UI. Public metadata only.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum LinkState {
    /// Dialing / handshaking; no authenticated session yet.
    Connecting,
    /// Authenticated session past the first projection ack.
    Online,
    /// Last session ended with a retryable error; waiting out the backoff.
    Reconnecting { attempt: u32 },
    /// Stopped retrying: a person must act (credentials, TLS trust, journal).
    NeedsOperator(AgentError),
    /// Stopped retrying: internal invariant failure.
    Failed(AgentError),
    /// Stopped on request.
    Stopped,
}

/// Handed to each session so it can report "handshake and first projection done".
#[derive(Clone)]
pub(super) struct SessionProbe(std::sync::Arc<ProbeInner>);
struct ProbeInner {
    established: std::sync::atomic::AtomicBool,
    soft_rejection: std::sync::atomic::AtomicBool,
    state: tokio::sync::watch::Sender<LinkState>,
}
impl SessionProbe {
    pub(super) fn established(&self) {
        self.0
            .established
            .store(true, std::sync::atomic::Ordering::SeqCst);
        self.0.state.send_replace(LinkState::Online);
    }
    /// The gateway answered the upgrade 403/404. Same `Authentication` error, but a
    /// restarting gateway (stop flag) or a proxy mid-deploy gives exactly these, so
    /// the supervisor retries them for a bounded time before asking for a person.
    pub(super) fn soft_rejection(&self) {
        self.0
            .soft_rejection
            .store(true, std::sync::atomic::Ordering::SeqCst);
    }
    fn was_soft_rejection(&self) -> bool {
        self.0
            .soft_rejection
            .load(std::sync::atomic::Ordering::SeqCst)
    }
    fn was_established(&self) -> bool {
        self.0.established.load(std::sync::atomic::Ordering::SeqCst)
    }
}

/// Protocol/backoff time compression. Production is always `REAL` (divisor 1);
/// only `#[cfg(test)]` code can change it, so real-socket fault tests finish fast.
#[derive(Clone, Copy)]
pub(super) struct Pacing {
    divisor: u32,
}
impl Pacing {
    pub(super) const REAL: Self = Self { divisor: 1 };
    #[cfg(all(test, unix))]
    pub(super) fn compressed(divisor: u32) -> Self {
        Self {
            divisor: divisor.max(1),
        }
    }
    fn scale(self, d: Duration) -> Duration {
        d / self.divisor
    }
}
/// Protocol timeouts (connect 10s, receive 12s, ack 10s, heartbeat 8s, projection 4s)
/// go through here. Identity in production; compressed by the fault tests only.
#[cfg(not(test))]
pub(super) fn scaled(d: Duration) -> Duration {
    d
}
#[cfg(test)]
pub(super) static TEST_TIME_DIVISOR: std::sync::atomic::AtomicU32 =
    std::sync::atomic::AtomicU32::new(1);
#[cfg(test)]
pub(super) fn scaled(d: Duration) -> Duration {
    d / TEST_TIME_DIVISOR
        .load(std::sync::atomic::Ordering::Relaxed)
        .max(1)
}

/// A session this long after its handshake counts as healthy: the retry counter
/// is cleared. Shorter flaps keep growing the backoff (no tight reconnect loop).
pub(super) const STABLE_AFTER: Duration = Duration::from_secs(30);
/// Consecutive 403/404 upgrade answers (no session in between) are retried at the
/// capped backoff for this long before they become `NeedsOperator`. 401 and TLS
/// trust errors are never soft: they stop at once.
pub(super) const SOFT_REJECT_LIMIT: Duration = Duration::from_secs(600);
/// Other errors (network noise, 5xx) between soft rejections do not restart the window,
/// but a quiet gap longer than this between two rejections does: they were not one outage.
pub(super) const SOFT_GAP: Duration = Duration::from_secs(120);
/// After the limit the rejection is shown as `NeedsOperator` (a person may fix it) but the
/// Agent keeps trying this often, so an outage that ends on its own still heals without
/// anyone pressing a button. Credential and TLS errors never get this: they stop at once.
pub(super) const SLOW_RETRY: Duration = Duration::from_secs(60);

/// Keep one session alive until asked to stop. Only `stop` or a non-retryable
/// error ends it: the 3600s `run_seconds`/server MAX_AGE rollover, a dropped
/// socket, a gateway restart and a sleeping desktop all just reconnect.
/// Reconnecting never replays work: that is the journal's and the cloud
/// admission ledger's decision, not this loop's.
pub(super) async fn supervise<F, Fut>(
    mut stop: tokio::sync::watch::Receiver<bool>,
    jitter: &dyn Jitter,
    state: &tokio::sync::watch::Sender<LinkState>,
    pacing: Pacing,
    mut session: F,
) -> Result<(), AgentError>
where
    F: FnMut(SessionProbe) -> Fut,
    Fut: std::future::Future<Output = Result<(), AgentError>>,
{
    let mut attempts = 0u32;
    // When the current unbroken run of soft (403/404) rejections began.
    let mut soft_since: Option<tokio::time::Instant> = None;
    let mut last_soft: Option<tokio::time::Instant> = None;
    // True from the first escalation until a session is established: the visible state
    // stays NeedsOperator (no Connecting/Reconnecting blinking) while we keep retrying.
    let mut slow = false;
    loop {
        if *stop.borrow() {
            state.send_replace(LinkState::Stopped);
            return Ok(());
        }
        if !slow {
            state.send_replace(LinkState::Connecting);
        }
        let probe = SessionProbe(std::sync::Arc::new(ProbeInner {
            established: std::sync::atomic::AtomicBool::new(false),
            soft_rejection: std::sync::atomic::AtomicBool::new(false),
            state: state.clone(),
        }));
        let started = tokio::time::Instant::now();
        let result = tokio::select! {
            biased;
            _ = stop.changed() => {
                state.send_replace(LinkState::Stopped);
                return Ok(());
            }
            r = session(probe.clone()) => r,
        };
        // A clean end (nobody asked for it) is reconnected like a dropped socket.
        let error = result.err().unwrap_or(AgentError::Transport);
        let soft = error == AgentError::Authentication
            && probe.was_soft_rejection()
            && !probe.was_established();
        let now = tokio::time::Instant::now();
        if soft {
            let same_outage = last_soft.is_some_and(|last| now - last <= pacing.scale(SOFT_GAP));
            if !(same_outage && soft_since.is_some()) {
                soft_since = Some(now);
            }
            last_soft = Some(now);
        } else if probe.was_established() {
            // Only a real session ends the streak; Transport noise alone does not.
            soft_since = None;
            last_soft = None;
            slow = false;
        }
        let soft_budget_left = soft
            && !slow
            && soft_since.is_some_and(|since| now - since < pacing.scale(SOFT_REJECT_LIMIT));
        if soft && !soft_budget_left {
            // A rejection that outlived the window: ask for a person, keep trying slowly.
            slow = true;
            state.send_replace(LinkState::NeedsOperator(error));
            let wait = SLOW_RETRY + SLOW_RETRY * (jitter.permille().min(1000) as u32) / 4000;
            tokio::select! {
                biased;
                _ = stop.changed() => {
                    state.send_replace(LinkState::Stopped);
                    return Ok(());
                }
                _ = tokio::time::sleep(pacing.scale(wait)) => {}
            }
            continue;
        }
        match classify_retry(error) {
            RetryClass::NeedsOperator if !soft_budget_left => {
                state.send_replace(LinkState::NeedsOperator(error));
                return Err(error);
            }
            RetryClass::NeedsOperator => {}
            RetryClass::Fatal => {
                state.send_replace(LinkState::Failed(error));
                return Err(error);
            }
            RetryClass::Retryable => {}
        }
        if probe.was_established() && started.elapsed() >= pacing.scale(STABLE_AFTER) {
            attempts = 0;
        }
        attempts = attempts.saturating_add(1);
        // Once NeedsOperator is shown it stays until a session is really up: other
        // transient errors in between must not make the state blink.
        if !slow {
            state.send_replace(LinkState::Reconnecting { attempt: attempts });
        }
        tokio::select! {
            biased;
            _ = stop.changed() => {
                state.send_replace(LinkState::Stopped);
                return Ok(());
            }
            _ = tokio::time::sleep(pacing.scale(backoff_delay(attempts, jitter.permille()))) => {}
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::AgentError::*;

    #[test]
    fn backoff_doubles_from_one_second_and_caps_at_thirty() {
        let secs: Vec<u64> = (1..=9).map(|n| backoff_base(n).as_secs()).collect();
        assert_eq!(secs, [1, 2, 4, 8, 16, 30, 30, 30, 30]);
        assert_eq!(backoff_base(0).as_secs(), 1);
        assert_eq!(backoff_base(u32::MAX).as_secs(), 30);
    }
    #[test]
    fn jitter_adds_at_most_a_quarter_and_never_subtracts() {
        assert_eq!(backoff_delay(1, 0), Duration::from_secs(1));
        assert_eq!(backoff_delay(1, 1000), Duration::from_millis(1250));
        assert_eq!(backoff_delay(6, 0), Duration::from_secs(30));
        assert_eq!(backoff_delay(6, 1000), Duration::from_millis(37_500));
        assert_eq!(backoff_delay(6, 9_999_999), Duration::from_millis(37_500));
    }
    #[test]
    fn system_jitter_stays_in_range_and_varies() {
        let j = SystemJitter;
        let samples: Vec<u64> = (0..64).map(|_| j.permille()).collect();
        assert!(samples.iter().all(|v| *v <= 1000));
        assert!(samples.iter().any(|v| *v != samples[0]));
    }

    #[test]
    fn recoverable_errors_are_retryable() {
        for e in [
            Transport,
            LocalAuthority,
            Capacity,
            Protocol,
            ExecutionUnknown,
        ] {
            assert_eq!(classify_retry(e), RetryClass::Retryable, "{e:?}");
        }
    }
    #[test]
    fn operator_fixable_errors_stop_retrying() {
        for e in [Configuration, Credentials, Journal, Authentication, Tls] {
            assert_eq!(classify_retry(e), RetryClass::NeedsOperator, "{e:?}");
        }
    }
    #[test]
    fn internal_invariant_errors_are_fatal() {
        for e in [Arguments, Cancelled, Exhausted, Duplicate] {
            assert_eq!(classify_retry(e), RetryClass::Fatal, "{e:?}");
        }
    }
    #[test]
    fn classification_is_total_over_agent_error() {
        // Adding an AgentError variant must force a conscious retry decision here.
        fn exhaustive(e: crate::AgentError) -> RetryClass {
            match e {
                Transport | LocalAuthority | Capacity | Protocol | ExecutionUnknown => {
                    RetryClass::Retryable
                }
                Configuration | Credentials | Journal | Authentication | Tls => {
                    RetryClass::NeedsOperator
                }
                Arguments | Cancelled | Exhausted | Duplicate => RetryClass::Fatal,
            }
        }
        for e in [
            Arguments,
            Configuration,
            Credentials,
            Journal,
            Protocol,
            Authentication,
            Tls,
            Transport,
            Exhausted,
            Cancelled,
            LocalAuthority,
            Capacity,
            Duplicate,
            ExecutionUnknown,
        ] {
            assert_eq!(classify_retry(e), exhaustive(e));
        }
    }

    // ---- supervise(): paused tokio time is the injectable clock ----
    use std::sync::{Arc, Mutex};
    use tokio::{sync::watch, time::Instant};

    struct FixedJitter(u64);
    impl Jitter for FixedJitter {
        fn permille(&self) -> u64 {
            self.0
        }
    }
    /// One scripted session: connect-handshake result, how long it lives, outcome.
    #[derive(Clone)]
    struct Step {
        established: bool,
        soft: bool,
        lives: Duration,
        outcome: Result<(), AgentError>,
    }
    fn step(established: bool, lives_s: u64, outcome: Result<(), AgentError>) -> Step {
        Step {
            established,
            soft: false,
            lives: Duration::from_secs(lives_s),
            outcome,
        }
    }
    /// An upgrade answered 403/404: Authentication, flagged as possibly temporary.
    fn soft() -> Step {
        Step {
            soft: true,
            ..step(false, 0, Err(Authentication))
        }
    }
    struct Harness {
        starts: Arc<Mutex<Vec<Instant>>>,
        state: watch::Receiver<LinkState>,
        stop: watch::Sender<bool>,
        task: tokio::task::JoinHandle<Result<(), AgentError>>,
    }
    /// After the script is exhausted every further session just stays up forever.
    fn launch(script: Vec<Step>, jitter: u64) -> Harness {
        let starts = Arc::new(Mutex::new(Vec::new()));
        let (stop, stop_rx) = watch::channel(false);
        let (state_tx, state) = watch::channel(LinkState::Connecting);
        let script = Arc::new(Mutex::new(std::collections::VecDeque::from(script)));
        let recorded = starts.clone();
        let task = tokio::spawn(async move {
            supervise(
                stop_rx,
                &FixedJitter(jitter),
                &state_tx,
                Pacing::REAL,
                move |probe| {
                    recorded.lock().unwrap().push(Instant::now());
                    let next = script.lock().unwrap().pop_front();
                    async move {
                        let Some(step) = next else {
                            probe.established();
                            return std::future::pending().await;
                        };
                        if step.soft {
                            probe.soft_rejection();
                        }
                        if step.established {
                            probe.established();
                        }
                        tokio::time::sleep(step.lives).await;
                        step.outcome
                    }
                },
            )
            .await
        });
        Harness {
            starts,
            state,
            stop,
            task,
        }
    }
    async fn settle() {
        for _ in 0..16 {
            tokio::task::yield_now().await;
        }
    }
    impl Harness {
        fn count(&self) -> usize {
            self.starts.lock().unwrap().len()
        }
        fn gaps_ms(&self) -> Vec<u128> {
            let s = self.starts.lock().unwrap();
            s.windows(2).map(|w| (w[1] - w[0]).as_millis()).collect()
        }
        /// Sleeping in the test body lets the paused runtime step timer by timer,
        /// so cascading reconnect timers fire in order (a single `advance` would not).
        async fn advance(&self, secs: u64) {
            tokio::time::sleep(Duration::from_secs(secs)).await;
            settle().await;
        }
    }

    #[tokio::test(start_paused = true)]
    async fn never_exits_at_or_after_the_3600_second_boundary() {
        let mut h = launch(vec![], 0);
        settle().await;
        h.advance(3599).await;
        assert!(!h.task.is_finished(), "exited before 3600s");
        h.advance(1).await;
        assert!(!h.task.is_finished(), "exited at 3600s");
        h.advance(1).await;
        assert!(!h.task.is_finished(), "exited at 3601s");
        h.advance(3700).await;
        assert!(!h.task.is_finished(), "exited at 7301s");
        assert_eq!(h.count(), 1, "a healthy session must not be restarted");
        h.stop.send(true).unwrap();
        assert_eq!((&mut h.task).await.unwrap(), Ok(()));
    }
    #[tokio::test(start_paused = true)]
    async fn more_than_eight_drops_after_stable_sessions_never_exhaust() {
        let script = (0..12).map(|_| step(true, 60, Err(Transport))).collect();
        let mut h = launch(script, 0);
        h.advance(12 * 61 + 10).await;
        assert!(!h.task.is_finished(), "gave up after repeated drops");
        assert_eq!(h.count(), 13);
        // Counter cleared by every stable session: always the 1s first-step delay.
        assert!(
            h.gaps_ms().iter().take(12).all(|g| *g == 61_000),
            "{:?}",
            h.gaps_ms()
        );
        h.stop.send(true).unwrap();
        assert_eq!((&mut h.task).await.unwrap(), Ok(()));
    }
    #[tokio::test(start_paused = true)]
    async fn handshake_failure_streak_backs_off_to_thirty_seconds_and_never_exhausts() {
        let script = (0..20).map(|_| step(false, 0, Err(Transport))).collect();
        let mut h = launch(script, 0);
        h.advance(20 * 31).await;
        assert!(!h.task.is_finished());
        assert_eq!(h.count(), 21);
        let g = h.gaps_ms();
        assert_eq!(
            &g[..8],
            &[1000, 2000, 4000, 8000, 16000, 30000, 30000, 30000]
        );
        assert!(g[5..].iter().all(|x| *x == 30_000));
        h.stop.send(true).unwrap();
        assert_eq!((&mut h.task).await.unwrap(), Ok(()));
    }
    #[tokio::test(start_paused = true)]
    async fn short_lived_established_sessions_do_not_reset_so_flapping_is_rate_limited() {
        let script = (0..7).map(|_| step(true, 5, Err(Transport))).collect();
        let mut h = launch(script, 0);
        h.advance(7 * 40).await;
        let g = h.gaps_ms();
        // 5s alive + 1,2,4,8,16,30,30 backoff: never a tight 1s reconnect loop.
        assert_eq!(&g[..7], &[6000, 7000, 9000, 13000, 21000, 35000, 35000]);
        h.stop.send(true).unwrap();
        (&mut h.task).await.unwrap().unwrap();
    }
    #[tokio::test(start_paused = true)]
    async fn session_that_outlives_the_stability_window_resets_the_counter() {
        let mut h = launch(
            vec![
                step(false, 0, Err(Transport)),
                step(false, 0, Err(Transport)),
                step(false, 0, Err(Transport)),
                step(true, 31, Err(Transport)),
                step(false, 0, Err(Transport)),
            ],
            0,
        );
        h.advance(200).await;
        let g = h.gaps_ms();
        assert_eq!(&g[..3], &[1000, 2000, 4000]);
        assert_eq!(g[3], 31_000 + 1000, "reset after a 31s stable session");
        // The reset happened once (1s after the stable session); the next unstable failure is attempt 2.
        assert_eq!(g[4], 2000);
        h.stop.send(true).unwrap();
        (&mut h.task).await.unwrap().unwrap();
    }
    #[tokio::test(start_paused = true)]
    async fn jitter_is_added_on_top_of_the_base_delay() {
        let mut h = launch(vec![step(false, 0, Err(Transport))], 1000);
        h.advance(5).await;
        assert_eq!(h.gaps_ms(), vec![1250]);
        h.stop.send(true).unwrap();
        (&mut h.task).await.unwrap().unwrap();
    }
    #[tokio::test(start_paused = true)]
    async fn recoverable_local_errors_are_retried_not_fatal() {
        let mut h = launch(
            vec![
                step(false, 0, Err(LocalAuthority)),
                step(false, 0, Err(Capacity)),
                step(false, 0, Err(Protocol)),
                step(false, 0, Err(ExecutionUnknown)),
                step(true, 0, Ok(())),
            ],
            0,
        );
        h.advance(100).await;
        assert!(!h.task.is_finished());
        assert_eq!(h.count(), 6);
        h.stop.send(true).unwrap();
        (&mut h.task).await.unwrap().unwrap();
    }
    #[tokio::test(start_paused = true)]
    async fn needs_operator_errors_stop_after_one_attempt_with_visible_state() {
        for e in [Authentication, Tls, Credentials, Configuration, Journal] {
            let mut h = launch(vec![step(false, 0, Err(e))], 0);
            assert_eq!((&mut h.task).await.unwrap(), Err(e));
            assert_eq!(*h.state.borrow(), LinkState::NeedsOperator(e));
        }
    }
    #[tokio::test(start_paused = true)]
    async fn needs_operator_after_reconnects_does_not_start_a_retry_storm() {
        let mut h = launch(
            vec![
                step(false, 0, Err(Transport)),
                step(false, 0, Err(Authentication)),
            ],
            0,
        );
        assert_eq!((&mut h.task).await.unwrap(), Err(Authentication));
        assert_eq!(h.count(), 2);
        // Nothing more is ever started, however long we wait.
        h.advance(3600).await;
        assert_eq!(h.count(), 2);
    }
    #[tokio::test(start_paused = true)]
    async fn soft_rejections_back_off_to_thirty_seconds_then_need_an_operator_but_keep_trying_slowly(
    ) {
        let h = launch(vec![soft(); 500], 0);
        // Just before the limit: still retrying, visibly, never a storm.
        h.advance(SOFT_REJECT_LIMIT.as_secs() - 5).await;
        assert!(!h.task.is_finished(), "escalated before the limit");
        assert!(matches!(
            *h.state.borrow(),
            LinkState::Reconnecting { .. } | LinkState::Connecting
        ));
        let before = h.count();
        assert!((20..=40).contains(&before), "attempts {before}");
        assert!(
            h.gaps_ms().iter().all(|g| *g <= 30_000),
            "{:?}",
            h.gaps_ms()
        );
        h.advance(40).await;
        // Past the limit a person is asked (visible NeedsOperator) but the Agent is not
        // abandoned: it keeps trying about once a minute, so an outage that ends on its
        // own still heals without anyone pressing a button.
        assert!(!h.task.is_finished(), "gave up instead of retrying slowly");
        assert_eq!(*h.state.borrow(), LinkState::NeedsOperator(Authentication));
        let total = h.count();
        h.advance(3600).await;
        let slow = h.count() - total;
        assert!(
            (55..=62).contains(&slow),
            "slow attempts in an hour: {slow}"
        );
        let gaps = h.gaps_ms();
        assert!(gaps.iter().rev().take(10).all(|g| *g == 60_000), "{gaps:?}");
        assert_eq!(*h.state.borrow(), LinkState::NeedsOperator(Authentication));
    }
    #[tokio::test(start_paused = true)]
    async fn slow_retry_after_the_limit_recovers_online_and_stops_on_request() {
        let mut script = vec![soft(); 40];
        script.push(step(true, 3600, Err(Transport)));
        let mut h = launch(script, 0);
        h.advance(SOFT_REJECT_LIMIT.as_secs() + 30).await;
        assert_eq!(*h.state.borrow(), LinkState::NeedsOperator(Authentication));
        // The remaining soft answers arrive one a minute; then a session comes up.
        h.advance(40 * 60).await;
        assert_eq!(*h.state.borrow(), LinkState::Online);
        h.stop.send(true).unwrap();
        assert_eq!((&mut h.task).await.unwrap(), Ok(()));
        assert_eq!(*h.state.borrow(), LinkState::Stopped);
    }
    #[tokio::test(start_paused = true)]
    async fn stop_during_the_slow_retry_wait_returns_ok() {
        let mut h = launch(vec![soft(); 500], 0);
        h.advance(SOFT_REJECT_LIMIT.as_secs() + 30).await;
        assert_eq!(*h.state.borrow(), LinkState::NeedsOperator(Authentication));
        h.stop.send(true).unwrap();
        assert_eq!((&mut h.task).await.unwrap(), Ok(()));
    }
    #[tokio::test(start_paused = true)]
    async fn a_401_or_tls_error_after_a_long_outage_still_needs_an_operator_at_once() {
        for e in [Authentication, Tls] {
            let mut script = vec![soft(); 40];
            script.push(step(false, 0, Err(e))); // a plain (not soft) rejection
            let mut h = launch(script, 0);
            h.advance(SOFT_REJECT_LIMIT.as_secs() + 30).await;
            h.advance(40 * 60).await;
            assert_eq!((&mut h.task).await.unwrap(), Err(e));
            assert_eq!(*h.state.borrow(), LinkState::NeedsOperator(e));
        }
    }
    #[tokio::test(start_paused = true)]
    async fn transport_noise_between_soft_rejections_does_not_reset_the_window() {
        // 403, network error, 403, network error ... A flapping link must not keep a
        // permanent rejection below the limit forever; only a real session resets it.
        let mut script = Vec::new();
        for _ in 0..300 {
            script.push(soft());
            script.push(step(false, 0, Err(Transport)));
        }
        let h = launch(script, 0);
        h.advance(SOFT_REJECT_LIMIT.as_secs() - 5).await;
        assert!(!h.task.is_finished(), "escalated before the limit");
        h.advance(60).await;
        assert_eq!(
            *h.state.borrow(),
            LinkState::NeedsOperator(Authentication),
            "403 flapping with Transport never escalated"
        );
        assert!(!h.task.is_finished(), "escalation must not end the Agent");
    }
    #[tokio::test(start_paused = true)]
    async fn a_long_quiet_gap_between_soft_rejections_starts_a_new_window() {
        // One 403, then ~15 minutes of plain network errors, then 403s again: two
        // separate incidents, so the second one gets its own full window.
        let mut script = vec![soft()];
        script.extend(vec![step(false, 0, Err(Transport)); 40]);
        script.extend(vec![soft(); 500]);
        let h = launch(script, 0);
        h.advance(1 + 1110 + 540).await; // 40 transports back off to ~1110s
        assert!(!h.task.is_finished(), "unrelated incidents were merged");
        // 540s into the second incident is still inside its own 600s window. Had the two
        // been merged, the first 403 (at t=0) would already be 1650s old: NeedsOperator.
        assert!(
            matches!(
                *h.state.borrow(),
                LinkState::Reconnecting { .. } | LinkState::Connecting
            ),
            "unrelated incidents were merged: {:?}",
            *h.state.borrow()
        );
        h.advance(100).await;
        assert_eq!(
            *h.state.borrow(),
            LinkState::NeedsOperator(Authentication),
            "the second incident never reached its own limit"
        );
    }
    #[tokio::test(start_paused = true)]
    async fn alternating_403_and_transport_errors_do_not_flap_the_visible_state() {
        // Past the limit, a gateway that answers 403 and a network that sometimes drops
        // must not make the link blink Reconnecting <-> NeedsOperator every minute or two.
        let mut script = vec![soft(); 40];
        for _ in 0..100 {
            script.push(soft());
            script.push(step(false, 0, Err(Transport)));
        }
        let h = launch(script, 0);
        h.advance(SOFT_REJECT_LIMIT.as_secs() + 30).await;
        assert_eq!(*h.state.borrow(), LinkState::NeedsOperator(Authentication));
        let mut seen = Vec::new();
        for _ in 0..1800 {
            h.advance(1).await;
            seen.push(*h.state.borrow());
        }
        assert!(
            seen.iter()
                .all(|s| *s == LinkState::NeedsOperator(Authentication)),
            "state left NeedsOperator without a session: {:?}",
            seen.iter()
                .filter(|s| **s != LinkState::NeedsOperator(Authentication))
                .take(3)
                .collect::<Vec<_>>()
        );
        assert!(!h.task.is_finished());
    }
    #[tokio::test(start_paused = true)]
    async fn a_quiet_gap_after_escalation_does_not_open_a_new_window_or_drop_needs_operator() {
        // Already escalated; the network then dies for >SOFT_GAP; the gateway answers 403
        // again. Still the same unresolved outage: no fresh 600s of Reconnecting.
        let mut script = vec![soft(); 30];
        script.extend(vec![step(false, 0, Err(Transport)); 12]);
        script.extend(vec![soft(); 100]);
        let h = launch(script, 0);
        h.advance(SOFT_REJECT_LIMIT.as_secs() + 30).await;
        assert_eq!(*h.state.borrow(), LinkState::NeedsOperator(Authentication));
        for _ in 0..1200 {
            h.advance(1).await;
            assert_eq!(
                *h.state.borrow(),
                LinkState::NeedsOperator(Authentication),
                "left NeedsOperator after count {}",
                h.count()
            );
        }
        // Still one minute apart, not a fresh run of fast backoff attempts (51 vs 59 here).
        assert!(
            h.count() <= 54,
            "retried too fast after the gap: {}",
            h.count()
        );
        assert!(!h.task.is_finished());
    }
    #[tokio::test(start_paused = true)]
    async fn only_an_established_session_leaves_needs_operator_and_a_later_drop_reconnects_normally(
    ) {
        let mut script = vec![soft(); 40];
        script.push(step(false, 0, Err(Transport)));
        script.push(step(true, 100, Err(Transport)));
        script.extend(vec![step(false, 0, Err(Transport)); 20]);
        let h = launch(script, 0);
        h.advance(SOFT_REJECT_LIMIT.as_secs() + 30).await;
        assert_eq!(*h.state.borrow(), LinkState::NeedsOperator(Authentication));
        // Run on until the session is up (the last soft answers come a minute apart).
        let mut online_seen = false;
        for _ in 0..(40 * 60 + 200) {
            h.advance(1).await;
            let now = *h.state.borrow();
            if now == LinkState::Online {
                online_seen = true;
            }
            if online_seen {
                break;
            }
        }
        assert!(online_seen, "never came back online");
        // The session later drops: a normal reconnect, not a stale NeedsOperator.
        h.advance(101).await;
        assert!(
            matches!(*h.state.borrow(), LinkState::Reconnecting { .. }),
            "{:?}",
            *h.state.borrow()
        );
    }
    #[tokio::test(start_paused = true)]
    async fn an_established_session_ends_the_soft_rejection_streak() {
        // ~3 minutes of 403s, then a session that really comes up and later drops,
        // then 9 more minutes of 403s: more than the limit in total, less in a row.
        let mut script = vec![soft(); 10];
        script.push(step(true, 40, Err(Transport)));
        script.extend(vec![soft(); 500]);
        let h = launch(script, 0);
        h.advance(181 + 40 + 9 * 60).await;
        assert!(!h.task.is_finished(), "streak was not reset by the session");
    }
    #[tokio::test(start_paused = true)]
    async fn a_403_from_a_restarting_gateway_recovers_without_operator_action() {
        let mut script = vec![soft(); 4];
        script.push(step(true, 3600, Err(Transport)));
        let h = launch(script, 0);
        h.advance(100).await;
        assert!(!h.task.is_finished());
        assert_eq!(*h.state.borrow(), LinkState::Online);
        assert_eq!(h.count(), 5);
    }
    #[tokio::test(start_paused = true)]
    async fn fatal_errors_stop_after_one_attempt_with_visible_state() {
        for e in [Duplicate, Arguments, Exhausted, Cancelled] {
            let mut h = launch(vec![step(false, 0, Err(e))], 0);
            assert_eq!((&mut h.task).await.unwrap(), Err(e));
            assert_eq!(*h.state.borrow(), LinkState::Failed(e));
        }
    }
    #[tokio::test(start_paused = true)]
    async fn stop_during_backoff_returns_ok_and_starts_no_further_session() {
        let mut h = launch(vec![step(false, 0, Err(Transport))], 0);
        settle().await;
        assert_eq!(h.count(), 1);
        h.stop.send(true).unwrap();
        assert_eq!((&mut h.task).await.unwrap(), Ok(()));
        assert_eq!(h.count(), 1);
        assert_eq!(*h.state.borrow(), LinkState::Stopped);
    }
    #[tokio::test(start_paused = true)]
    async fn link_state_tracks_connecting_online_and_reconnecting() {
        let mut h = launch(vec![step(true, 40, Err(Transport))], 0);
        settle().await;
        assert_eq!(*h.state.borrow(), LinkState::Online);
        h.advance(40).await;
        assert_eq!(*h.state.borrow(), LinkState::Reconnecting { attempt: 1 });
        h.advance(1).await;
        assert_eq!(*h.state.borrow(), LinkState::Online);
        h.stop.send(true).unwrap();
        (&mut h.task).await.unwrap().unwrap();
    }
}
