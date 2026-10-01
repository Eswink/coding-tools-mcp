"""Validate a reported journal without authenticating it or permitting replay."""
from rc_pretag_types import require
from rc_publication_contract import asset_matches, classify_inventory, recipe_fingerprint, release_matches
from rc_publication_types import JournalObservation, ObservationReport, fresh

DRAFTS = ('draft_empty_reported', 'draft_partial_reported', 'draft_complete_reported')


def reconcile(journal):
    journal = fresh(journal, JournalObservation)
    recipe = journal.recipe
    require(journal.recipe_fingerprint == recipe_fingerprint(recipe), 'journal_recipe_mismatch')
    expected = {asset.name: asset for asset in recipe.assets}
    accounted, attempted = {}, set()
    public_baseline = None
    seen_releases, seen_assets = set(), set()
    reasons = []
    rid, last_classification = None, None
    conflict = stopped = uncertain = failed = published = needs_checkpoint = False

    def reason(code):
        if code not in reasons:
            reasons.append(code)

    def problem(code):
        nonlocal conflict, stopped
        conflict, stopped = True, True
        reason(code)

    def observe_release(release):
        nonlocal published
        if release is not None:
            seen_releases.add(release.release_id)
            seen_assets.update(asset.asset_id for asset in release.assets)
            if release.source == recipe.source and release.tag == recipe.release_tag and not release.draft:
                published = True

    for index, entry in enumerate(journal.entries, 1):
        if entry.sequence != index:
            problem('journal_order')
        if index == 1 and entry.kind != 'checkpoint':
            problem('checkpoint_required')
        if entry.kind == 'checkpoint':
            checkpoint = entry.checkpoint
            was_published = published
            for release in checkpoint.releases:
                observe_release(release)
            result = classify_inventory(recipe, checkpoint)
            for code in result.reasons:
                reason(code)
            if index == 1:
                last_classification = result.classification
                if result.classification in DRAFTS:
                    release = checkpoint.releases[0]
                    rid = release.release_id
                    accounted = {asset.name: asset for asset in release.assets}
                elif result.classification == 'published_complete_reported':
                    rid = checkpoint.releases[0].release_id
                    public_baseline = {asset.name: asset for asset in checkpoint.releases[0].assets}
                    reason('published_observation')
                elif result.classification == 'collision':
                    problem('checkpoint_conflict')
                elif result.classification != 'absent_reported':
                    stopped = True
                    reason('initial_inventory_unknown')
                continue
            if was_published and result.classification in DRAFTS:
                problem('checkpoint_conflict')
                continue
            if stopped:
                # Reconciliation may report new IDs after an unknown result.
                # Retain them, but never make them successful-operation IDs.
                if result.classification == 'collision':
                    reason('checkpoint_conflict')
                continue
            if result.classification not in (*DRAFTS, 'published_complete_reported', 'absent_reported'):
                if result.classification == 'collision':
                    problem('checkpoint_conflict')
                else:
                    stopped = True
                    reason('initial_inventory_unknown')
                continue
            if rid is None:
                if result.classification != 'absent_reported':
                    problem('journal_target')
                last_classification = result.classification
                continue
            if (not checkpoint.releases or checkpoint.expected_release_id != rid
                    or checkpoint.releases[0].release_id != rid):
                problem('journal_target')
                continue
            release = checkpoint.releases[0]
            baseline = public_baseline if public_baseline is not None else accounted
            if {asset.name: asset for asset in release.assets} != baseline:
                problem('unaccounted_asset')
                continue
            if result.classification == 'published_complete_reported':
                reason('published_observation')
            last_classification = result.classification
            needs_checkpoint = False
            continue

        attempt = entry.attempt
        was_published = published
        observe_release(attempt.response_release)
        if attempt.response_asset is not None:
            seen_assets.add(attempt.response_asset.asset_id)
        # Keep outcome facts even when the surrounding trace is contradictory.
        if attempt.outcome in ('prepared_only', 'outcome_unknown'):
            uncertain = True
            reason('uncertain_outcome')
        if attempt.outcome == 'response_failure':
            failed = True
            reason('failed_attempt')
        if stopped or was_published:
            problem('operation_after_stop')
            continue
        if needs_checkpoint or last_classification is None:
            problem('checkpoint_required')
            continue
        key = (attempt.operation, attempt.asset_name)
        if key in attempted:
            problem('journal_replay')
            continue
        attempted.add(key)
        if attempt.operation == 'create_draft':
            if rid is not None or last_classification != 'absent_reported':
                problem('journal_target')
                continue
        elif rid is None or attempt.release_id != rid or last_classification not in DRAFTS:
            problem('journal_target')
            continue
        if attempt.operation == 'upload_asset':
            if attempt.asset_name not in expected:
                problem('response_conflict')
                continue
            if attempt.asset_name in accounted:
                problem('journal_replay')
                continue
        if attempt.operation == 'publish' and (
                len(accounted) != 6 or last_classification != 'draft_complete_reported'):
            problem('checkpoint_required')
            continue
        if attempt.outcome != 'response_success':
            stopped = True
            continue
        if attempt.operation == 'upload_asset':
            asset = attempt.response_asset
            if (not asset_matches(expected[attempt.asset_name], asset)
                    or asset.asset_id in {row.asset_id for row in accounted.values()}):
                problem('response_conflict')
                continue
            accounted[asset.name] = asset
        else:
            release = attempt.response_release
            wanted_draft = attempt.operation == 'create_draft'
            if (not release_matches(recipe, release) or release.draft is not wanted_draft
                    or (rid is not None and release.release_id != rid)
                    or {asset.name: asset for asset in release.assets} != accounted
                    or len(release.assets) != len(accounted)):
                problem('response_conflict')
                continue
            rid = release.release_id
        needs_checkpoint = True

    if needs_checkpoint and not stopped:
        reason('checkpoint_required')
        reason('incomplete_journal')
    classification = 'journal_conflict' if conflict else (
        'journal_stopped' if stopped or needs_checkpoint else 'journal_consistent')
    return ObservationReport(classification, tuple(reasons), published_observed=published,
                             uncertainty_observed=uncertain, failed_observed=failed,
                             release_id=rid,
                             accounted_asset_ids=tuple(sorted(row.asset_id for row in accounted.values())),
                             observed_release_ids=tuple(sorted(seen_releases)),
                             observed_asset_ids=tuple(sorted(seen_assets)))
