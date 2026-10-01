"""Synthetic recipe and inventory consistency only; never live visibility evidence."""
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import unittest

from rc_pretag_types import ContractError, encode, parse_json
from rc_publication_contract import classify_inventory, recipe_fingerprint, validate_recipe
from rc_publication_fixtures import (assert_unverified, synthetic_asset, synthetic_assets,
    synthetic_checkpoint, synthetic_recipe, synthetic_recipe_and_checksums, synthetic_release)
from rc_publication_types import DOMAIN, InventoryCheckpoint, PublicationRecipe


class PublicationRecipeTests(unittest.TestCase):
    def test_exact_synthetic_recipe_checksums_and_deep_copy(self):
        recipe, checksums = synthetic_recipe_and_checksums()
        result = validate_recipe(recipe, checksums)
        self.assertEqual(result, recipe)
        self.assertIsNot(result, recipe)
        self.assertIsNot(result.source, recipe.source)
        self.assertIsNot(result.assets[0], recipe.assets[0])
        assert_unverified(self, result)
        self.assertEqual(len(checksums.splitlines()), 5)
        self.assertNotIn(recipe.assets[-1].name.encode(), checksums)

    def test_fingerprint_uses_exact_domain_and_canonical_encoding(self):
        recipe = synthetic_recipe()
        digest = recipe_fingerprint(recipe)
        self.assertEqual(digest, sha256(b'rc-publication-contract/v1:recipe\n' + encode(recipe)).hexdigest())
        self.assertEqual(DOMAIN, b'rc-publication-contract/v1:recipe\n')
        self.assertNotEqual(digest, sha256(encode(recipe)).hexdigest())
        self.assertEqual(digest, recipe_fingerprint(parse_json(PublicationRecipe, encode(recipe))))
        assert_unverified(self, recipe)

    def test_every_content_identity_change_changes_fingerprint(self):
        recipe = synthetic_recipe()
        changes = (replace(recipe, notes_sha256='f' * 64),
                   replace(recipe, consumer_plan_sha256='f' * 64),
                   replace(recipe, source=replace(recipe.source, source_sha='f' * 40)),
                   replace(recipe, source=replace(recipe.source, source_tree='f' * 40)),
                   replace(recipe, assets=(replace(recipe.assets[0], size=123),) + recipe.assets[1:]),
                   replace(recipe, assets=(replace(recipe.assets[0], sha256='f' * 64),) + recipe.assets[1:]))
        for changed in changes:
            self.assertNotEqual(recipe_fingerprint(recipe), recipe_fingerprint(changed))
            assert_unverified(self, changed)

    def test_checksum_grammar_coverage_order_and_alias_attacks(self):
        recipe, raw = synthetic_recipe_and_checksums()
        lines = raw.splitlines(keepends=True)
        attacks = (raw.replace(b'  ', b' ', 1), raw.replace(b'  ', b' *', 1),
                   raw.replace(b'\n', b'\r\n'), raw[:-1], raw + b'\n', b''.join(lines[::-1]),
                   b''.join(lines[1:]), raw + lines[0], raw.replace(lines[0], lines[1], 1),
                   lines[0].upper() + b''.join(lines[1:]),
                   raw.replace(b'MCP_', b'mcp_', 1), raw.replace(b'MCP_', b'../MCP_', 1),
                   raw.replace(b'MCP_', 'ＭCP_'.encode(), 1), raw +
                   f'{recipe.assets[-1].sha256}  {recipe.assets[-1].name}\n'.encode())
        for index, attack in enumerate(attacks):
            # Match the checksum asset itself so coverage/grammar must still be checked.
            checksum = replace(recipe.assets[-1], size=len(attack), sha256=sha256(attack).hexdigest())
            rebound = replace(recipe, assets=recipe.assets[:-1] + (checksum,))
            with self.subTest(attack=index), self.assertRaises(ContractError):
                validate_recipe(rebound, attack)

    def test_checksum_digest_and_size_bind_exact_bytes(self):
        recipe, raw = synthetic_recipe_and_checksums()
        for field, value in (('size', len(raw) + 1), ('sha256', '0' * 64)):
            checksum = replace(recipe.assets[-1], **{field: value})
            with self.assertRaisesRegex(ContractError, 'checksum_bytes_mismatch'):
                validate_recipe(replace(recipe, assets=recipe.assets[:-1] + (checksum,)), raw)
        changed = replace(recipe.assets[0], sha256='0' * 64)
        with self.assertRaises(ContractError):
            validate_recipe(replace(recipe, assets=(changed,) + recipe.assets[1:]), raw)

    def test_checksum_input_type_size_and_non_ascii_rejected(self):
        recipe, raw = synthetic_recipe_and_checksums()
        for value in (None, raw.decode(), bytearray(raw), b'', b'\xff', b'x' * 8193):
            with self.subTest(value=type(value).__name__), self.assertRaises(ContractError):
                validate_recipe(recipe, value)

    def test_entrypoints_reject_nested_frozen_record_tampering(self):
        original, checksums = synthetic_recipe_and_checksums()
        for field, value in (('name', '../token'), ('size', True), ('media_type', 'text/plain'),
                             ('sha256', 'X' * 64)):
            recipe = deepcopy(original)
            object.__setattr__(recipe.assets[0], field, value)
            for call in (lambda: validate_recipe(recipe, checksums), lambda: recipe_fingerprint(recipe),
                         lambda: classify_inventory(recipe, synthetic_checkpoint())):
                with self.assertRaises(ContractError):
                    call()
        recipe = deepcopy(original)
        object.__setattr__(recipe, 'assets', recipe.assets[::-1])
        with self.assertRaises(ContractError):
            recipe_fingerprint(recipe)

    def test_entrypoints_reject_forged_authority_or_missing_blockers(self):
        original, checksums = synthetic_recipe_and_checksums()
        for field, value in (('execution_enabled', True), ('release_approved', True),
                ('publish_approved', True), ('snapshot_atomic', True), ('blockers', ()),
                ('evidence_authentication', 'verified')):
            recipe = deepcopy(original)
            object.__setattr__(recipe, field, value)
            for call in (lambda: validate_recipe(recipe, checksums), lambda: recipe_fingerprint(recipe),
                         lambda: classify_inventory(recipe, synthetic_checkpoint())):
                with self.assertRaises(ContractError):
                    call()

    def test_public_entrypoints_accept_only_exact_reviewed_classes(self):
        class RecipeSubclass(PublicationRecipe):
            pass
        recipe, checksums = synthetic_recipe_and_checksums()
        subclass = RecipeSubclass(**{field: getattr(recipe, field) for field in recipe.__dataclass_fields__})
        for value in (None, {}, subclass):
            for call in (lambda: validate_recipe(value, checksums), lambda: recipe_fingerprint(value),
                         lambda: classify_inventory(value, synthetic_checkpoint())):
                with self.assertRaises(ContractError):
                    call()


class PublicationInventoryTests(unittest.TestCase):
    def classify(self, checkpoint, expected, reason=None):
        result = classify_inventory(synthetic_recipe(), checkpoint)
        assert_unverified(self, result)
        self.assertEqual(result.classification, expected)
        if reason is not None:
            self.assertIn(reason, result.reasons)
        # Inventory observations alone never establish successful attempt ownership.
        self.assertEqual(result.accounted_asset_ids, ())
        return result

    def test_explicit_reported_absence_is_unverified(self):
        result = self.classify(synthetic_checkpoint(), 'absent_reported')
        self.assertEqual(result.observed_release_ids, ())
        self.assertEqual(result.observed_asset_ids, ())
        self.assertIs(result.published_observed, False)

    def test_draft_empty_partial_and_complete_are_distinct(self):
        for count, expected in ((0, 'draft_empty_reported'), (1, 'draft_partial_reported'),
                                (5, 'draft_partial_reported'), (6, 'draft_complete_reported')):
            result = self.classify(synthetic_checkpoint(synthetic_release(synthetic_assets(count))), expected)
            self.assertEqual(result.observed_asset_ids, tuple(range(1001, 1001 + count)))
            self.assertEqual(result.observed_release_ids, (700,))
            self.assertIs(result.published_observed, False)

    def test_published_complete_is_observation_only(self):
        result = self.classify(synthetic_checkpoint(synthetic_release(synthetic_assets(), draft=False)),
                              'published_complete_reported')
        self.assertIs(result.published_observed, True)
        self.assertEqual(result.release_id, 700)

    def test_published_partial_and_empty_are_conflicts(self):
        for count in (0, 1, 5):
            result = self.classify(synthetic_checkpoint(synthetic_release(synthetic_assets(count), draft=False)),
                                  'collision', 'published_partial')
            self.assertIs(result.published_observed, True)

    def test_absence_needs_both_visibility_and_completeness(self):
        for visibility in ('unknown', 'denied'):
            self.classify(synthetic_checkpoint(visibility=visibility), 'unknown', 'visibility_unproven')
        for completeness in ('unknown', 'incomplete'):
            self.classify(synthetic_checkpoint(completeness=completeness), 'unknown', 'inventory_incomplete')

    def test_found_rows_do_not_bypass_unknown_visibility_or_incomplete_listing(self):
        for field, value, reason in (('visibility', 'denied', 'visibility_unproven'),
                ('visibility', 'unknown', 'visibility_unproven'),
                ('completeness', 'incomplete', 'inventory_incomplete'),
                ('completeness', 'unknown', 'inventory_incomplete')):
            checkpoint = replace(synthetic_checkpoint(synthetic_release(synthetic_assets())), **{field: value})
            result = self.classify(checkpoint, 'unknown', reason)
            self.assertEqual(len(result.observed_asset_ids), 6)

    def test_unknown_and_inaccessible_are_never_inferred_absent(self):
        for lookup, reason in (('unknown', 'lookup_unknown'), ('inaccessible', 'target_inaccessible')):
            self.classify(synthetic_checkpoint(lookup=lookup), 'unknown', reason)

    def test_missing_target_is_unknown_matching_target_never_authenticates(self):
        release = replace(synthetic_release(), reported_target_commitish=None)
        self.classify(synthetic_checkpoint(release), 'unknown', 'target_unresolved')
        self.classify(synthetic_checkpoint(synthetic_release()), 'draft_empty_reported')

    def test_source_tree_commit_tag_notes_prerelease_and_target_mismatches(self):
        original = synthetic_release(synthetic_assets())
        changes = ({'source': replace(original.source, source_tree='f' * 40)},
                   {'source': replace(original.source, source_sha='f' * 40)},
                   {'source': replace(original.source, version='1.2.3-rc.8')},
                   {'tag': 'v1.2.3-rc.8'}, {'reported_target_commitish': 'f' * 40},
                   {'notes_sha256': 'f' * 64}, {'prerelease': False})
        for change in changes:
            self.classify(synthetic_checkpoint(replace(original, **change)), 'collision', 'release_mismatch')

    def test_checkpoint_identity_and_expected_release_id_are_bound(self):
        item = synthetic_checkpoint(synthetic_release())
        for change in ({'source': replace(item.source, source_tree='f' * 40)},
                       {'tag': 'v1.2.3-rc.8'}, {'expected_release_id': 701}):
            self.classify(replace(item, **change), 'collision', 'release_mismatch')
        self.classify(synthetic_checkpoint(expected_release_id=700), 'collision', 'release_mismatch')

    def test_multiple_releases_collide_and_retain_ids(self):
        checkpoint = synthetic_checkpoint(synthetic_release())
        checkpoint = replace(checkpoint, releases=(synthetic_release(), synthetic_release(release_id=701)))
        result = self.classify(checkpoint, 'collision', 'multiple_releases')
        self.assertEqual(result.observed_release_ids, (700, 701))
        self.classify(replace(checkpoint, releases=(synthetic_release(),) * 2), 'collision', 'multiple_releases')

    def test_duplicate_asset_names_or_ids_are_collisions(self):
        asset = synthetic_asset()
        for other in (replace(asset, asset_id=1007), synthetic_asset(1, asset_id=asset.asset_id), asset):
            self.classify(synthetic_checkpoint(synthetic_release((asset, other))), 'collision', 'asset_duplicate')

    def test_extra_renamed_case_alias_and_foreign_version_assets_collide(self):
        for name in ('extra.txt', synthetic_asset().name.lower(), 'MCP_1.2.3-rc.8_x64-setup.exe'):
            extra = replace(synthetic_asset(), name=name, asset_id=2000)
            result = self.classify(synthetic_checkpoint(synthetic_release(synthetic_assets() + (extra,))),
                                  'collision', 'asset_extra')
            self.assertIn(2000, result.observed_asset_ids)

    def test_missing_mime_size_or_digest_stays_incomplete(self):
        for field in ('media_type', 'size', 'sha256'):
            asset = replace(synthetic_asset(), **{field: None})
            self.classify(synthetic_checkpoint(synthetic_release((asset,))), 'unknown', 'asset_incomplete')

    def test_wrong_mime_size_digest_zero_or_nonuploaded_state_conflicts(self):
        for field, value in (('media_type', 'text/plain'), ('size', 1), ('sha256', 'f' * 64),
                             ('size', 0), ('state', 'starter'), ('state', 'unknown')):
            asset = replace(synthetic_asset(), **{field: value})
            self.classify(synthetic_checkpoint(synthetic_release((asset,))), 'collision', 'asset_conflict')

    def test_observed_asset_order_does_not_change_identity_match(self):
        self.classify(synthetic_checkpoint(synthetic_release(synthetic_assets()[::-1])), 'draft_complete_reported')

    def test_nested_inventory_tampering_is_deeply_revalidated(self):
        for field, value in (('asset_id', True), ('size', 2 * 1024**3 + 1), ('name', '../file')):
            checkpoint = synthetic_checkpoint(synthetic_release((synthetic_asset(),)))
            object.__setattr__(checkpoint.releases[0].assets[0], field, value)
            with self.assertRaises(ContractError):
                classify_inventory(synthetic_recipe(), checkpoint)
        checkpoint = synthetic_checkpoint(synthetic_release())
        object.__setattr__(checkpoint.releases[0].source, 'source_tree', 'X' * 40)
        with self.assertRaises(ContractError):
            classify_inventory(synthetic_recipe(), checkpoint)

    def test_checkpoint_subclass_and_untyped_inputs_rejected(self):
        class CheckpointSubclass(InventoryCheckpoint):
            pass
        item = synthetic_checkpoint()
        subclass = CheckpointSubclass(**{field: getattr(item, field) for field in item.__dataclass_fields__})
        for value in (None, {}, subclass):
            with self.assertRaises(ContractError):
                classify_inventory(synthetic_recipe(), value)


if __name__ == '__main__':
    unittest.main()
