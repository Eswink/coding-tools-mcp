"""Fixed non-executable evidence requirements; no row has a live verifier yet."""
from dataclasses import dataclass

from rc_pretag_types import POLICY_REVISION, PERMISSIONS, require, sequence

# Canonical ledger reviewed alongside the consumer baseline; no live lookup occurs.
CURRENT_LEDGER_SOURCE_SHA = 'e2e011f7f2a3a1df838bbd588106205b999db610'
CURRENT_ISSUE_IDS = frozenset(('#32', '#33', '#34', '#37', '#38', '#39', '#40', '#41',
    '#42', '#43', '#44', '#45', '#46', '#70', '#73', '#81', '#84', '#85', '#86', '#87', '#88'))
ROOT = 'GET /repos/Eswink/coding-tools-mcp'
SOURCE_READS = (ROOT, ROOT + '/git/ref/heads/{fixed_ref}', ROOT + '/git/commits/{source_sha}',
                ROOT + '/git/trees/{source_tree}', ROOT + '/git/blobs/{reviewed_manifest_blob}')
RUN_READS = (ROOT + '/actions/workflows/{fixed_workflow}/runs?head_sha={source_sha}',
             ROOT + '/actions/runs/{run_id}',
             ROOT + '/actions/runs/{run_id}/attempts/{run_attempt}/jobs',
             ROOT + '/actions/runs/{run_id}/artifacts', ROOT + '/actions/artifacts/{artifact_id}',
             ROOT + '/actions/artifacts/{artifact_id}/zip')
REVIEW_READS = (ROOT + '/pulls/36', ROOT + '/pulls/36/reviews',
                ROOT + '/pulls/36/reviews/{review_id}', ROOT + '/pulls/36/commits')
RELEASE_READS = (ROOT + '/releases', ROOT + '/releases/{known_release_id}')


@dataclass(frozen=True)
class GateRequirement:
    gate_id: str
    scope: str
    ledger_rows: tuple[str, ...]
    endpoints: tuple[str, ...]
    artifact_contract: str
    permissions: tuple[str, ...]
    visibility: str
    identity_binding: str
    completeness: str
    failure_semantics: str
    freshness: str
    verifier: str = 'unimplemented'

    def __post_init__(self):
        for value in (self.ledger_rows, self.endpoints, self.permissions):
            sequence(value, str, 16)
        require(all(p in PERMISSIONS for p in self.permissions), 'invalid_policy_permission')
        require(self.verifier == 'unimplemented', 'unsupported_policy_verifier')


def requirement(key, scope, ledger, family='engineering', contract='unmapped producer; blocked'):
    endpoints = RUN_READS
    permissions = ('contents:read', 'actions:read')
    visibility = 'authenticated same-repository run/job/artifact visibility; no label-based proof'
    completeness = 'newest same-source run across all statuses; exact current-attempt jobs; bounded complete lists'
    identity = 'repository ID/name, source SHA/tree, workflow, run/current attempt/job and API ZIP digest/size'
    if family == 'source':
        endpoints, permissions = SOURCE_READS, ('contents:read',)
        if key == 'tag_absence':
            endpoints += (ROOT + '/git/ref/tags/{strict_tag}',)
        visibility = 'successful surrounding repository/ref visibility; a permission-shaped404 is unknown'
        completeness = 'clean immutable source, six versions, gateway version and frozen reviewed manifest'
    elif family == 'review':
        endpoints, permissions = REVIEW_READS, ('contents:read', 'pull-requests:read')
        visibility = 'authenticated reviewer/PR visibility; no implicit public fallback after denial'
        identity = 'numeric reviewer/review ID, submitted non-dismissed review, reviewed SHA, current PR head/merge SHA/tree'
        completeness = 'complete reviews/commits; exact-tree receipt provenance remains unmapped and blocked'
    elif family == 'release':
        endpoints, permissions = RELEASE_READS, ('contents:read',)
        visibility = 'same-principal known existing draft direct/list proof; nominal scope or empty list is insufficient'
        completeness = 'fully paginated inventory plus independently established draft visibility; no dummy draft'
    elif family == 'invocation':
        endpoints = SOURCE_READS + RUN_READS[:3]
        contract = 'real reviewed fixed post-merge integration invocation is unavailable; candidate/main push is insufficient'
    return GateRequirement(key, scope, ledger, endpoints, contract, permissions, visibility, identity,
        completeness, 'missing/denied/truncated/stale/failed/skipped/unknown => blocked; no older-green fallback',
        'repeat source/run/current attempt/job/artifact/visibility observations at every admission fence; non-atomic')


# Each original ledger row is explicitly covered. No closure/status text is evidence.
_LEDGER_ENGINEERING = (
    ('epic_scope', '#32', 'Full36-item cloud/Agent/native roadmap and cumulative acceptance'),
    ('architecture', '#33', 'Threat model, dependency, architecture and rollback equivalence'),
    ('protocol', '#34', 'Modern/legacy MCP and HostAgent protocol/error contracts'),
    ('oauth', '#37', 'PKCE, single-use refresh, replay, concurrency and restart'),
    ('local_authority', '#38', 'Native owner approval, scope/epoch/expiry/revoke/drain/foreign denial'),
    ('enrollment', '#39', 'Device proof, single-use/domain/lock-wait expiry and restart'),
    ('deployment_topology', '#40', 'Existing-Nginx nonproduction topology, privateDB and nonroot exact images'),
    ('owner_login', '#41', 'Cookies/Origin/CSRF/fixation/deny/rotation/restart'),
    ('gateway_provisioning', '#42', 'Protected provisioning, explicit migration and bounded lifecycle'),
    ('signed_projection', '#43', 'Signed grant bounds/races/revoke/restore and owner transfer after drain'),
    ('agent_channel', '#44', 'TLS/WSS/proof/generation/restart/disconnect/rollback equivalence'),
    ('browser_origin', '#45', 'Origin negatives, real browser referrer policy without rewritten headers'),
    ('control_fencing', '#46', 'Durable tombstones/unknown restart/late replies and upgraded WS drain'),
    ('managed_worktrees', '#70', 'Dirty/staged/untracked/ignored/path/reparse/hardlink/idempotency and no Git hooks'),
    ('linux_isolation', '#73', 'Mandatory Ubuntu22/24 filesystem/network/PTY/process/boundedIO and fail-closed positives'),
    ('native_bridge', '#81', 'Full native cloud/Agent/runtime acceptance with no replay or authority widening'),
    ('npm_audit', '#84', 'Locked dependency integrity, real npm audit and malformed-input regression'),
    ('rust_audit', '#85', 'RawRustSec plus target/features/binary/provenance and TLS/WSS negatives'),
    ('snapshot_root_authority', '#86', 'Required opened-root handle authority and deterministic native race contracts'),
    ('rc_tag_routing', '#87', 'Actual13-job FINAL inventory, lightweight tag event and unchanged stable guards'),
    ('protocol_scope_ci', 'LEDGER-CI-01', 'Exact source/changed-path gate and original protocol/offline assertions'),
    ('clean_versions', 'LEDGER-CI-02', 'Clean-tree and six-version positive/negative final-source regressions'),
    ('cumulative_regressions', 'LEDGER-CI-03', 'Exact Windows/Ubuntu cumulative regressions with no skipped positives'),
    ('health_socket', 'LEDGER-CI-HEALTH-01', 'Health socket ownership and unchanged discovery assertions'),
    ('source_assembly', 'LEDGER-SOURCE-01', 'Cumulative source ancestry/tree/blob equivalence and frozen manifest'),
    ('listener_recovery', 'LEDGER-SOURCE-02', 'Listener source/receipt/export recovery and current-source evidence'),
    ('draft_reconciliation', 'LEDGER-PR-01', 'Overlapping draft equivalence and required scope coverage'),
    ('windows_isolation', 'LEDGER-RUNTIME-01', 'Real Windows positive execution, filesystem/network/cancel/PTY and admission'),
    ('hooks', 'LEDGER-RUNTIME-02', 'Native approved exact scripts, before/after/cancel/failure/dedup and UI'),
    ('snapshots', 'LEDGER-RUNTIME-03', 'Native capture/restore/recovery, metadata/ACL and protected-path contracts'),
    ('foundation_scope', 'LEDGER-EVIDENCE-01', 'Closed35/47/49/50/51 behavior mapped to exact current-source evidence'),
    ('installed_packages', 'LEDGER-PACKAGE-01', 'Three installers, four cloud binaries and five installed-native rows'),
    ('owner_version', 'LEDGER-VERSION', 'Explicit owner version semantics; stable/desktop collisions are not candidates'),
    ('async_hook_dedup', 'LEDGER-ASYNC-01', 'Outer/inner/concurrent/restart/failedHook no replay and cancel/revoke'),
    ('root_storage', 'LEDGER-ROOT-TEST-01', 'Cold/unknown/uncertain durable root identity and storage lifetime'),
    ('formatting', 'LEDGER-FMT-01', 'Full formatting and regressions on final cumulative source'),
    ('durable_latency', 'LEDGER-LATENCY-01', 'Real key lock/duplicate/disconnect/restart/busloss and unchanged deadlines'),
    ('capability_truth', 'LEDGER-CAPABILITY-01', 'Remote Windows unavailable/refusal and Linux per-child unknown semantics'),
)
_EXTRA_ENGINEERING = (
    ('windows_execution', 'Windows approved runtime positive execution without broader capabilities'),
    ('windows_denial', 'Windows outside-root read/write and network denial; startup failure is not denial'),
    ('windows_cancel', 'Windows cancel/revoke/process-tree termination and durable admission'),
    ('windows_pty', 'Windows PTY bounded IO/capacity/lifecycle and original positive contracts'),
    ('windows_hooks', 'Windows actual approved before/after Hooks and no duplicate mutation'),
    ('windows_snapshot', 'Windows full snapshot security metadata, restore/recovery and root authority'),
    ('windows_warnings', 'Windows production warnings-as-errors including original snapshot warnings'),
    ('ubuntu22_isolation', 'Ubuntu22 mandatory isolation positives, negatives, PTY/cancel/process-tree'),
    ('ubuntu24_isolation', 'Ubuntu24 mandatory isolation positives, negatives, PTY/cancel/process-tree'),
    ('raw_cloud_audit', 'Authenticated raw cloud audit streams and exact build active applicability'),
    ('raw_noncloud_audits', 'Authenticated desktop/local-agent/cloud-agent locks, raw audits and paired upstream GLib proof'),
    ('installed_five_rows', 'Windows NSIS, Ubuntu22/24 DEB and Ubuntu22/24 AppImage exact native twelve-stage matrix'),
    ('structural_blocker_resolution', 'Unchanged structural blocker text plus independent exact-source resolution; no resolver exists'),
)
GATES = tuple(requirement(key, scope, (ledger, 'LEDGER-CI-RC-TAG-01') if ledger == '#87'
                          else (ledger,)) for key, ledger, scope in _LEDGER_ENGINEERING) + tuple(
    requirement(key, scope, ()) for key, scope in _EXTRA_ENGINEERING) + (
    requirement('source_manifest', 'Immutable source/tree/version/frozen reviewed manifest', (), 'source'),
    requirement('tag_absence', 'Local/remote prospective lightweight tag absent', (), 'source',
                'GET fixed strict-tag ref with independently established genuine-not-found semantics'),
    requirement('full_integration', 'Exact seven successful newest integration jobs', (), contract='dot-rc-integration.yml; seven exact names'),
    requirement('final_packaging', 'Exact thirteen successful newest FINAL jobs, push, attempt1', (), contract='final-rc-packages.yml; thirteen exact names'),
    requirement('bundle_bytes', 'API-authenticated FINAL ZIP before bounded parsing', (), contract='rc-structural-bundle API digest/size and four payload/five installed contracts'),
    requirement('storage_host', 'Frozen proved exact storage host and token-free outer ZIP', (), contract='source-pinned storage policy; unseen host blocks without retry-as-success'),
    requirement('pretag_invocation', 'Actual source-bound pretag push/workflow/blob identity', (), 'source'),
    requirement('postmerge_integration_invocation', 'Supported real post-merge full integration route', (), 'invocation'),
    requirement('main_integration', 'Reviewed PR36 merged exact source/tree; new SHA invalidates prior runs', (), 'review'),
    requirement('final_independent_review', 'Authorized exact-tree independent final review provenance', (), 'review'),
    requirement('release_collisions', 'No draft or published tag/version collision', (), 'release'),
    requirement('draft_visibility', 'Actual same-principal draft visibility independently proven', (), 'release'),
)
GATE_IDS = tuple(row.gate_id for row in GATES)
require(len(set(GATE_IDS)) == len(GATE_IDS), 'duplicate_policy_gate')

# These remain visible without inventing an impossible pre-tag circular dependency.
LATER_PHASE_ROWS = (
    ('#88', 'blocked', 'Full consumer/publisher acceptance requires separate later post-tag and public-byte proof; no circular pre-tag dependency'),
    ('LEDGER-PUBLISH-01', 'blocked', 'Separate reviewed mutation and anonymous download acceptance'),
)
DEFERRED_ROWS = (('LEDGER-HOST', 'deferred', 'Physical workstation/VPS/real ChatGPT remain unverified'),)
OPTIONAL_OBSERVATIONS = ('tag_protection', 'platform_release_immutability')
