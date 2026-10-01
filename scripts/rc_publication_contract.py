"""Pure consistency checks; supplied recipes and inventories remain unverified."""
import hashlib

from rc_pretag_types import encode, require
from rc_publication_types import (DOMAIN, InventoryCheckpoint, ObservationReport,
                                  PublicationRecipe, fresh)

__all__ = ('validate_recipe', 'recipe_fingerprint', 'classify_inventory')


def recipe_fingerprint(recipe):
    recipe = fresh(recipe, PublicationRecipe)
    return hashlib.sha256(DOMAIN + encode(recipe)).hexdigest()


def validate_recipe(recipe, checksums):
    recipe = fresh(recipe, PublicationRecipe)
    require(type(checksums) is bytes and 0 < len(checksums) <= 8192, 'invalid_checksum_bytes')
    expected = ''.join(f'{asset.sha256}  {asset.name}\n'
                       for asset in sorted(recipe.assets[:-1], key=lambda item: item.name)).encode('ascii')
    require(checksums == expected, 'checksum_inventory_mismatch')
    checksum = recipe.assets[-1]
    require(checksum.size == len(checksums)
            and checksum.sha256 == hashlib.sha256(checksums).hexdigest(), 'checksum_bytes_mismatch')
    return recipe


def asset_matches(expected, observed):
    """Internal helper: records are already revalidated; equality grants no authority."""
    return (observed.name == expected.name and observed.state == 'uploaded'
            and observed.size == expected.size and observed.sha256 == expected.sha256
            and observed.media_type == expected.media_type)


def release_matches(recipe, release):
    """Internal, prevalidated claimed equality; never authenticate a tag or authority."""
    return (release.source == recipe.source and release.tag == recipe.release_tag
            and release.reported_target_commitish == recipe.source.source_sha
            and release.prerelease is True and release.notes_sha256 == recipe.notes_sha256)


def classify_inventory(recipe, checkpoint):
    recipe = fresh(recipe, PublicationRecipe)
    checkpoint = fresh(checkpoint, InventoryCheckpoint)
    releases = checkpoint.releases
    seen_releases = tuple(sorted({row.release_id for row in releases}))
    seen_assets = tuple(sorted({asset.asset_id for row in releases for asset in row.assets}))
    published = any(not row.draft and row.tag == recipe.release_tag for row in releases)
    rid = releases[0].release_id if len(releases) == 1 else None

    def report(classification, *reasons):
        return ObservationReport(classification, tuple(dict.fromkeys(reasons)),
                                 published_observed=published, release_id=rid,
                                 observed_release_ids=seen_releases, observed_asset_ids=seen_assets)

    if checkpoint.source != recipe.source or checkpoint.tag != recipe.release_tag:
        return report('collision', 'release_mismatch')
    if len(releases) > 1:
        return report('collision', 'multiple_releases')
    if releases:
        release = releases[0]
        if (release.source != recipe.source or release.tag != recipe.release_tag
                or release.prerelease is not True or release.notes_sha256 != recipe.notes_sha256
                or (release.reported_target_commitish is not None
                    and release.reported_target_commitish != recipe.source.source_sha)
                or (checkpoint.expected_release_id is not None
                    and checkpoint.expected_release_id != release.release_id)):
            return report('collision', 'release_mismatch')
    reasons = []
    if checkpoint.visibility != 'reported_visible':
        reasons.append('visibility_unproven')
    if checkpoint.completeness != 'complete':
        reasons.append('inventory_incomplete')
    if checkpoint.lookup == 'inaccessible':
        reasons.append('target_inaccessible')
    elif checkpoint.lookup == 'unknown':
        reasons.append('lookup_unknown')
    if reasons:
        return report('unknown', *reasons)
    if checkpoint.lookup == 'absent':
        if checkpoint.expected_release_id is not None:
            return report('collision', 'release_mismatch')
        return report('absent_reported')
    release = releases[0]
    if release.reported_target_commitish is None:
        return report('unknown', 'target_unresolved')
    assets = release.assets
    if len({row.name for row in assets}) != len(assets) or len({row.asset_id for row in assets}) != len(assets):
        return report('collision', 'asset_duplicate')
    expected = {asset.name: asset for asset in recipe.assets}
    if any(row.name not in expected for row in assets):
        return report('collision', 'asset_extra')
    incomplete = False
    for asset in assets:
        if asset.state != 'uploaded' or asset.size == 0:
            return report('collision', 'asset_conflict')
        if asset.size is None or asset.sha256 is None or asset.media_type is None:
            incomplete = True
        elif not asset_matches(expected[asset.name], asset):
            return report('collision', 'asset_conflict')
    if incomplete:
        return report('unknown', 'asset_incomplete')
    complete = len(assets) == 6
    if not release.draft:
        return report('published_complete_reported' if complete else 'collision',
                      *(() if complete else ('published_partial',)))
    if complete:
        return report('draft_complete_reported')
    return report('draft_partial_reported' if assets else 'draft_empty_reported')
