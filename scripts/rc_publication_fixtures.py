"""Synthetic observations only; no fixture authenticates evidence or grants authority."""
from dataclasses import replace
from hashlib import sha256

from rc_pretag_evidence import payload_names
from rc_pretag_types import REPOSITORY, REPOSITORY_ID, SourceIdentity, encode
from rc_publication_types import (AssetObservation, AssetSpec, AttemptObservation, BLOCKERS,
    DOMAIN, FAMILIES, InventoryCheckpoint, JournalEntry, JournalObservation, MEDIA,
    PublicationRecipe, ReleaseObservation)


def synthetic_source():
    return SourceIdentity(REPOSITORY, REPOSITORY_ID, 'a' * 40, 'b' * 40, '1.2.3-rc.7')


def synthetic_recipe_and_checksums():
    source = synthetic_source()
    names = tuple(payload_names(source.version).values()) + ('RC_PROVENANCE.json',)
    assets = tuple(AssetSpec(name, family, media, len(body), sha256(body).hexdigest())
        for name, family, media, body in zip(names, FAMILIES, MEDIA,
            (b'synthetic nsis', b'synthetic deb', b'synthetic appimage',
             b'synthetic cloud', b'{"synthetic":true}\n')))
    checksums = b''.join(f'{a.sha256}  {a.name}\n'.encode('ascii')
                         for a in sorted(assets, key=lambda a: a.name))
    checksum = AssetSpec(f'SHA256SUMS_{source.version}.txt', 'checksums', MEDIA[-1],
                         len(checksums), sha256(checksums).hexdigest())
    return PublicationRecipe(source, 'v' + source.version, assets + (checksum,),
                             'c' * 64, 'd' * 64), checksums


def synthetic_recipe():
    return synthetic_recipe_and_checksums()[0]


def synthetic_asset(index=0, *, recipe=None, asset_id=None):
    recipe = synthetic_recipe() if recipe is None else recipe
    spec = recipe.assets[index]
    return AssetObservation(1001 + index if asset_id is None else asset_id, spec.name,
                            'uploaded', spec.media_type, spec.size, spec.sha256)


def synthetic_assets(count=6, *, recipe=None):
    return tuple(synthetic_asset(i, recipe=recipe) for i in range(count))


def synthetic_release(assets=(), *, recipe=None, release_id=700, draft=True):
    recipe = synthetic_recipe() if recipe is None else recipe
    return ReleaseObservation(recipe.source, release_id, recipe.release_tag,
                               recipe.source.source_sha, draft, True,
                               recipe.notes_sha256, tuple(assets))


def synthetic_checkpoint(release=None, *, recipe=None, expected_release_id=None,
                         visibility='reported_visible', completeness='complete',
                         lookup=None):
    recipe = synthetic_recipe() if recipe is None else recipe
    releases = () if release is None else (release,)
    lookup = ('absent' if release is None else 'found') if lookup is None else lookup
    return InventoryCheckpoint(recipe.source, recipe.release_tag, expected_release_id,
                                visibility, completeness, lookup, releases)


def synthetic_attempt(operation='create_draft', outcome='response_success', *,
                      release_id=700, index=0, response=None, recipe=None):
    recipe = synthetic_recipe() if recipe is None else recipe
    if response is None and outcome == 'response_success':
        response = (synthetic_asset(index, recipe=recipe) if operation == 'upload_asset'
                    else synthetic_release(() if operation == 'create_draft' else
                         synthetic_assets(recipe=recipe), recipe=recipe,
                         release_id=release_id, draft=operation == 'create_draft'))
    upload = operation == 'upload_asset'
    return AttemptObservation(operation, None if operation == 'create_draft' else release_id,
        recipe.assets[index].name if upload else None, outcome,
        None if upload else operation == 'create_draft', None if upload else True,
        None if upload else 'false', None if upload else response, response if upload else None)


def synthetic_entries(*observations):
    return tuple(JournalEntry(index, 'attempt' if type(item) is AttemptObservation else
        'checkpoint', item if type(item) is AttemptObservation else None,
        item if type(item) is InventoryCheckpoint else None)
        for index, item in enumerate(observations, 1))


def synthetic_journal(*observations, recipe=None, transaction_digest='e' * 64):
    recipe = synthetic_recipe() if recipe is None else recipe
    return JournalObservation(recipe.source, recipe, sha256(DOMAIN + encode(recipe)).hexdigest(),
        transaction_digest, synthetic_entries(*(observations or (synthetic_checkpoint(),))))


def synthetic_full_trace(*, initial_count=None, publish=True):
    """A synthetic trace, never evidence that an operation actually ran."""
    recipe = synthetic_recipe()
    count = 0 if initial_count is None else initial_count
    assets = synthetic_assets(count, recipe=recipe)
    release = synthetic_release(assets, recipe=recipe)
    if initial_count is None:
        trace = [synthetic_checkpoint(recipe=recipe),
                 synthetic_attempt(recipe=recipe, response=release),
                 synthetic_checkpoint(release, recipe=recipe, expected_release_id=700)]
    else:
        trace = [synthetic_checkpoint(release, recipe=recipe, expected_release_id=700)]
    for index in range(count, 6):
        asset = synthetic_asset(index, recipe=recipe)
        trace.append(synthetic_attempt('upload_asset', index=index, response=asset, recipe=recipe))
        assets += (asset,)
        release = synthetic_release(assets, recipe=recipe)
        trace.append(synthetic_checkpoint(release, recipe=recipe, expected_release_id=700))
    if publish:
        release = replace(release, draft=False)
        trace += [synthetic_attempt('publish', response=release, recipe=recipe),
                  synthetic_checkpoint(release, recipe=recipe, expected_release_id=700)]
    return synthetic_journal(*trace, recipe=recipe)


def assert_unverified(testcase, result):
    testcase.assertEqual(result.evidence_authentication, 'unverified')
    testcase.assertEqual(result.blockers, BLOCKERS)
    for field in ('execution_enabled', 'release_approved', 'publish_approved', 'snapshot_atomic'):
        testcase.assertIs(getattr(result, field), False, field)
    testcase.assertEqual(encode(result), encode(type(result)(**{
        field: getattr(result, field) for field in result.__dataclass_fields__})))
