"""Strict synthetic record/codec tests; no authenticated or live publication evidence."""
from copy import deepcopy
from dataclasses import FrozenInstanceError, asdict, replace
import json
import unittest

from rc_pretag_types import ContractError, MAX_JSON_BYTES, decode, encode, parse_json
from rc_publication_fixtures import (assert_unverified, synthetic_asset, synthetic_assets,
    synthetic_attempt, synthetic_checkpoint, synthetic_full_trace, synthetic_journal,
    synthetic_recipe, synthetic_release)
from rc_publication_types import (AssetObservation, AssetSpec, AttemptObservation, BLOCKERS,
    InventoryCheckpoint, JournalEntry, JournalObservation, ObservationReport, PublicationRecipe,
    ReleaseObservation, fresh)


class PublicationTypeTests(unittest.TestCase):
    def reject(self, item, **changes):
        with self.assertRaises(ContractError):
            replace(item, **changes)

    def records(self):
        journal = synthetic_full_trace()
        return (synthetic_recipe().assets[0], synthetic_recipe(), synthetic_asset(),
                synthetic_release(), synthetic_checkpoint(), synthetic_attempt(),
                journal.entries[0], journal, ObservationReport('unknown', ('lookup_unknown',)))

    def test_all_exact_records_strict_roundtrip(self):
        for item in self.records():
            with self.subTest(record=type(item).__name__):
                self.assertEqual(parse_json(type(item), encode(item)), item)
                self.assertEqual(fresh(item, type(item)), item)

    def test_all_envelopes_keep_fixed_non_authority_boundary(self):
        for item in (synthetic_recipe(), synthetic_journal(), ObservationReport('unknown', ())):
            assert_unverified(self, item)
            for field in ('execution_enabled', 'release_approved', 'publish_approved',
                          'snapshot_atomic'):
                for value in (True, 0, 1, None, 'false'):
                    self.reject(item, **{field: value})
            for value in ('authenticated', 'verified', None, True):
                self.reject(item, evidence_authentication=value)

    def test_every_fixed_blocker_required_exactly_once_in_order(self):
        for item in (synthetic_recipe(), synthetic_journal(), ObservationReport('unknown', ())):
            for blockers in ((), BLOCKERS[:-1], BLOCKERS[::-1], BLOCKERS + (BLOCKERS[0],),
                             list(BLOCKERS), ('resolved',)):
                self.reject(item, blockers=blockers)

    def test_schema_rejects_boolean_float_and_unknown_revision(self):
        for item in (synthetic_recipe(), synthetic_journal(), ObservationReport('unknown', ())):
            for value in (True, False, 1.0, '1', 0, 2, None):
                self.reject(item, schema=value)
        self.reject(synthetic_recipe(), policy_revision='rc-publication-approved')

    def test_records_are_frozen_and_collections_are_tuples(self):
        for item in self.records():
            field = next(iter(item.__dataclass_fields__))
            with self.assertRaises(FrozenInstanceError):
                setattr(item, field, None)
        self.assertIsInstance(synthetic_recipe().assets, tuple)
        self.assertIsInstance(synthetic_full_trace().entries, tuple)
        self.assertIsInstance(synthetic_release().assets, tuple)

    def test_every_field_required_and_extension_fields_rejected(self):
        for item in self.records():
            for field in item.__dataclass_fields__:
                raw = asdict(item)
                del raw[field]
                with self.subTest(record=type(item).__name__, field=field):
                    with self.assertRaises(ContractError):
                        parse_json(type(item), json.dumps(raw).encode())
            raw = json.loads(encode(item))
            raw['next_action'] = 'publish'
            with self.assertRaises(ContractError):
                decode(type(item), raw)

    def test_duplicate_json_keys_at_top_and_nested_levels(self):
        recipe = encode(synthetic_recipe())
        for raw in (recipe.replace(b'"schema":1', b'"schema":1,"schema":1'),
                    recipe.replace(b'"repository_id":', b'"repository_id":1,"repository_id":')):
            with self.assertRaisesRegex(ContractError, 'duplicate_json_key'):
                parse_json(PublicationRecipe, raw)

    def test_nonfinite_and_malformed_json_and_wrong_input_types(self):
        for raw in (b'{"x":NaN}', b'{"x":Infinity}', b'{"x":-Infinity}',
                    b'\xff', b'{} garbage', b'null', b'[]', '{}', bytearray(b'{}')):
            with self.subTest(raw=repr(raw)), self.assertRaises(ContractError):
                parse_json(PublicationRecipe, raw)

    def test_json_byte_depth_array_object_string_limits(self):
        cases = (b' ' * (MAX_JSON_BYTES + 1), b'[' * 18 + b']' * 18,
                 json.dumps({'x': [0] * 129}).encode(),
                 json.dumps({str(i): i for i in range(129)}).encode(),
                 json.dumps({'x': 'x' * 513}).encode())
        for raw in cases:
            with self.assertRaises(ContractError):
                parse_json(JournalObservation, raw)

    def test_nested_extensions_and_boolean_integer_coercion_rejected(self):
        for path, field, value in ((('source',), 'repository_id', True),
                (('assets', 0), 'size', True), (('assets', 0), 'size', 1.0),
                (('assets', 0), 'authenticated', True), (('source',), 'extra', None)):
            raw = json.loads(encode(synthetic_recipe()))
            target = raw
            for part in path:
                target = target[part]
            target[field] = value
            with self.assertRaises(ContractError):
                decode(PublicationRecipe, raw)

    def test_nested_tampering_is_rejected_on_reencoding(self):
        for item, target, field, value in ((synthetic_recipe(), 'source', 'source_tree', 'X' * 40),
                (synthetic_journal(), 'recipe', 'publish_approved', True)):
            object.__setattr__(getattr(item, target), field, value)
            with self.assertRaises(ContractError):
                encode(item)
        item = synthetic_full_trace()
        object.__setattr__(item.entries[1].attempt.response_release, 'release_id', True)
        with self.assertRaises(ContractError):
            encode(item)

    def test_wrong_exact_record_types_and_subclasses_rejected(self):
        class RecipeSubclass(PublicationRecipe):
            pass
        item = synthetic_recipe()
        forged = RecipeSubclass(**{field: getattr(item, field) for field in item.__dataclass_fields__})
        for value in (forged, asdict(item), None, synthetic_journal()):
            with self.assertRaises(ContractError):
                fresh(value, PublicationRecipe)
        self.reject(item, source=asdict(item.source))
        self.reject(item, assets=list(item.assets))

    def test_asset_spec_bounds_and_exact_numeric_types(self):
        recipe = synthetic_recipe()
        for spec in recipe.assets:
            for value in (True, False, 1.0, '1', 0, -1):
                self.reject(spec, size=value)
            limit = 2 * 1024**3 if spec.family in ('nsis', 'deb', 'appimage', 'cloud') else (
                256 * 1024 if spec.family == 'provenance' else 8192)
            self.assertEqual(replace(spec, size=limit).size, limit)
            self.reject(spec, size=limit + 1)

    def test_names_digest_and_media_are_canonical(self):
        item = synthetic_recipe().assets[0]
        for name in ('../file', '/file', 'https://x.invalid/a', 'a b', 'é.exe', '', 'a' * 129):
            self.reject(item, name=name)
        for digest in ('A' * 64, 'g' * 64, 'a' * 63, 'a' * 65, True, None):
            self.reject(item, sha256=digest)
        for media in ('application/octet-stream', 'Application/vnd.microsoft.portable-executable', None):
            self.reject(item, media_type=media)
        self.reject(item, family='unknown')

    def test_recipe_exact_family_order_names_tag_and_six_assets(self):
        item = synthetic_recipe()
        for assets in (item.assets[:-1], item.assets + (item.assets[0],), item.assets[::-1],
                       item.assets[:1] + (item.assets[0],) + item.assets[2:]):
            self.reject(item, assets=assets)
        renamed = replace(item.assets[0], name=item.assets[0].name.lower())
        self.reject(item, assets=(renamed,) + item.assets[1:])
        for tag in ('v1.2.3', '1.2.3-rc.7', 'v1.2.3-rc.8', None):
            self.reject(item, release_tag=tag)

    def test_observed_ids_and_sizes_have_strict_bounds(self):
        for item, field in ((synthetic_asset(), 'asset_id'), (synthetic_release(), 'release_id'),
                            (synthetic_checkpoint(), 'expected_release_id'),
                            (synthetic_full_trace().entries[0], 'sequence')):
            for value in (True, False, 1.0, '1', 0, -1, 2**63):
                self.reject(item, **{field: value})
            self.assertEqual(getattr(replace(item, **{field: 2**63 - 1}), field), 2**63 - 1)
        for value in (None, 0, 2 * 1024**3):
            self.assertEqual(replace(synthetic_asset(), size=value).size, value)
        for value in (True, 1.0, '1', -1, 2 * 1024**3 + 1):
            self.reject(synthetic_asset(), size=value)

    def test_incomplete_asset_properties_remain_explicitly_optional(self):
        asset = replace(synthetic_asset(), media_type=None, size=None, sha256=None, state='unknown')
        self.assertEqual(parse_json(AssetObservation, encode(asset)), asset)
        for field, value in (('media_type', 'text/😀'), ('sha256', 'wrong'), ('state', 'complete')):
            self.reject(asset, **{field: value})

    def test_release_boolean_flags_and_optional_reported_target(self):
        item = synthetic_release()
        for field in ('draft', 'prerelease'):
            for value in (0, 1, 'true', None):
                self.reject(item, **{field: value})
        self.assertIsNone(replace(item, reported_target_commitish=None).reported_target_commitish)
        for value in ('main', 'A' * 40, 'a' * 39):
            self.reject(item, reported_target_commitish=value)

    def test_inventory_bounds_and_lookup_consistency(self):
        item = synthetic_release()
        self.assertEqual(len(replace(item, assets=(synthetic_asset(),) * 16).assets), 16)
        self.reject(item, assets=(synthetic_asset(),) * 17)
        found = synthetic_checkpoint(item)
        self.assertEqual(len(replace(found, releases=(item,) * 2).releases), 2)
        self.reject(found, releases=(item,) * 3)
        self.reject(found, releases=())
        self.reject(synthetic_checkpoint(), releases=(item,))
        for field in ('visibility', 'completeness', 'lookup'):
            self.reject(found, **{field: 'verified'})

    def test_attempt_intent_has_no_implicit_latest_or_stable_release(self):
        for operation in ('create_draft', 'publish'):
            item = synthetic_attempt(operation)
            for field, value in (('requested_draft', not item.requested_draft),
                ('requested_draft', int(item.requested_draft)), ('requested_prerelease', False),
                ('requested_prerelease', 1), ('requested_make_latest', 'true'),
                ('requested_make_latest', False), ('asset_name', synthetic_asset().name),
                ('response_asset', synthetic_asset())):
                self.reject(item, **{field: value})
        upload = synthetic_attempt('upload_asset')
        for field, value in (('requested_draft', True), ('requested_prerelease', True),
                ('requested_make_latest', 'false'), ('response_release', synthetic_release())):
            self.reject(upload, **{field: value})

    def test_attempt_target_response_and_outcome_shapes(self):
        self.reject(synthetic_attempt(), release_id=700)
        self.reject(synthetic_attempt('upload_asset'), release_id=None)
        self.reject(synthetic_attempt('publish'), release_id=None)
        for operation in ('create_draft', 'upload_asset', 'publish'):
            item = synthetic_attempt(operation)
            field = 'response_asset' if operation == 'upload_asset' else 'response_release'
            self.reject(item, **{field: None})
            self.reject(item, outcome='prepared_only')
            self.reject(item, outcome='retryable')
        self.reject(synthetic_attempt(), operation='delete')

    def test_journal_wrapper_exactly_one_payload_and_bounded_entries(self):
        item = synthetic_journal().entries[0]
        self.reject(item, attempt=synthetic_attempt())
        self.reject(item, checkpoint=None)
        self.reject(item, kind='attempt')
        self.reject(item, kind='request')
        journal = synthetic_journal()
        self.reject(journal, entries=())
        self.reject(journal, entries=(item,) * 33)
        self.assertEqual(len(replace(journal, entries=(item,) * 32).entries), 32)
        self.reject(journal, source=replace(journal.source, source_tree='f' * 40))

    def test_report_reasons_flags_and_id_bounds(self):
        item = ObservationReport('unknown', ('lookup_unknown',))
        for reasons in (('authorized',), ('lookup_unknown',) * 2, ['lookup_unknown']):
            self.reject(item, reasons=reasons)
        for field in ('published_observed', 'uncertainty_observed', 'failed_observed'):
            for value in (0, 1, None, 'false'):
                self.reject(item, **{field: value})
        for field, limit in (('accounted_asset_ids', 6), ('observed_release_ids', 64),
                             ('observed_asset_ids', 128)):
            self.reject(item, **{field: (True,)})
            self.reject(item, **{field: (1, 1)})
            self.reject(item, **{field: tuple(range(1, limit + 2))})
            self.assertEqual(len(getattr(replace(item, **{field: tuple(range(1, limit + 1))}),
                                             field)), limit)
        self.reject(item, classification='approved')

    def test_large_finite_json_exponents_cannot_coerce_to_integer_or_boolean(self):
        raw = encode(synthetic_recipe())
        for value in (b'1e9999', b'-1e9999', b'1.0', b'true'):
            changed = raw.replace(b'"schema":1', b'"schema":' + value)
            with self.assertRaises(ContractError):
                parse_json(PublicationRecipe, changed)

    def test_journal_identity_digests_use_strict_sha256_grammar(self):
        journal = synthetic_journal()
        for field in ('recipe_fingerprint', 'transaction_digest'):
            for value in ('A' * 64, 'g' * 64, 'a' * 63, 'a' * 65, None, True):
                self.reject(journal, **{field: value})


if __name__ == '__main__':
    unittest.main()
