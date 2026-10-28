import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from romancer import contracts


class AdapterInventoryTests(unittest.TestCase):
    def test_inventory_declares_all_five_adapters_without_runtime_authority(self):
        result = contracts.adapter_inventory()
        self.assertTrue(result["ok"])
        self.assertEqual(result["schema_version"], 2)
        self.assertEqual(result["scope"], "adapter_inventory")
        self.assertFalse(result["write_authorized"])
        adapters = {entry["id"]: entry for entry in result["adapters"]}
        self.assertEqual(set(adapters), {"nes", "snes", "genesis", "gb", "gbc", "sms"})
        for identifier, entry in adapters.items():
            with self.subTest(adapter=identifier):
                caps = entry["capabilities"]
                self.assertEqual(caps["raw_inspection"]["status"], "supported")
                self.assertEqual(caps["runtime_control"]["status"], "unavailable")
                self.assertEqual(caps["structured_resource_write"]["status"], "unsupported")
                self.assertEqual(caps["expert_payload_write"]["status"], "unsupported")
                for capability in caps.values():
                    self.assertIn(capability["status"], {"supported", "experimental", "unsupported", "unavailable"})
                    self.assertTrue(capability["reason"])
                    self.assertTrue(capability["implementation"])
        self.assertEqual(adapters["snes"]["capabilities"]["identification"]["status"], "experimental")

    def test_inventory_cannot_be_mutated_through_a_previous_response(self):
        first = contracts.adapter_inventory()
        first["adapters"][0]["capabilities"]["runtime_control"]["status"] = "supported"
        self.assertEqual(contracts.adapter_inventory()["adapters"][0]["capabilities"]["runtime_control"]["status"], "unavailable")


class ProfileContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="romancer contract fixture ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.artifact = self.root / "synthetic artifact.bin"
        self.artifact.write_bytes(b"ABCD")

    def profile(self, **changes):
        result = {"schema_version": 2, "id": "synthetic", "version": "1", "system": "nes",
                  "accepted_sha256": [hashlib.sha256(b"ABCD").hexdigest()],
                  "rules": [{"resource": "text", "offset": 1, "length": 2, "expected_hex": "4243"}]}
        result.update(changes)
        return result

    def test_exact_revision_and_rule_pass_without_modifying_any_input(self):
        profile = self.profile()
        original = copy.deepcopy(profile)
        result = contracts.check_contract(profile, self.artifact)
        self.assertTrue(result["ok"])
        self.assertTrue(result["revision_match"])
        self.assertEqual(result["artifact_sha256"], hashlib.sha256(b"ABCD").hexdigest())
        self.assertEqual(result["scope"], "profile_preconditions")
        self.assertEqual(result["schema_version"], 2)
        self.assertTrue(result["tool_version"])
        self.assertEqual(result["profile_id"], "synthetic")
        self.assertEqual(result["profile_version"], "1")
        self.assertFalse(result["write_authorized"])
        self.assertEqual(profile, original)
        self.assertEqual(self.artifact.read_bytes(), b"ABCD")
        self.assertEqual(list(self.root.iterdir()), [self.artifact])

    def test_validation_is_canonical_and_not_edit_authorization(self):
        profile = self.profile(provenance={"b": [True, None, 1.5], "a": "synthetic"})
        result = contracts.validate_contract(profile)
        reordered = dict(reversed(list(profile.items())))
        reordered["accepted_sha256"] = [profile["accepted_sha256"][0].upper()]
        self.assertTrue(result["ok"])
        self.assertEqual(result["scope"], "profile_schema")
        self.assertFalse(result["write_authorized"])
        self.assertRegex(result["profile_sha256"], r"^[0-9a-f]{64}$")
        expected_hash = hashlib.sha256(json.dumps(profile, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")).hexdigest()
        self.assertEqual(result["profile_sha256"], expected_hash)
        self.assertEqual(result["profile_sha256"], contracts.validate_contract(reordered)["profile_sha256"])
        profile["version"] = "2"
        self.assertNotEqual(result["profile_sha256"], contracts.validate_contract(profile)["profile_sha256"])

    def test_exact_schema_and_versions_reject_unknown_or_missing_fields(self):
        bad = [None, [], {}, self.profile(schema_version=True), self.profile(schema_version=2.0),
               self.profile(schema_version=1), self.profile(system="SNES"), self.profile(system="unknown"),
               self.profile(id=""), self.profile(version=" "), self.profile(version=1), self.profile(extra=True)]
        for field in self.profile():
            candidate = self.profile()
            del candidate[field]
            bad.append(candidate)
        for candidate in bad:
            with self.subTest(candidate=candidate), self.assertRaises(ValueError):
                contracts.validate_contract(candidate)

    def test_revisions_must_be_complete_nonempty_unique_digests(self):
        digest = self.profile()["accepted_sha256"][0]
        for values in ([], digest, [True], ["f" * 63], ["g" * 64], [digest, digest.upper()]):
            with self.subTest(values=values), self.assertRaises(ValueError):
                contracts.validate_contract(self.profile(accepted_sha256=values))

    def test_rule_types_lengths_hex_and_exact_fields_are_strict(self):
        rule = self.profile()["rules"][0]
        changes = ({"offset": True}, {"offset": -1}, {"offset": 1.0}, {"length": True},
                   {"length": 0}, {"length": -1}, {"length": 1048577}, {"expected_hex": "42 43"},
                   {"expected_hex": "424"}, {"expected_hex": "424x"}, {"expected_hex": True},
                   {"resource": ""}, {"resource": []}, {"resource": "line\nbreak"}, {"extra": 1})
        for change in changes:
            with self.subTest(change=change), self.assertRaises(ValueError):
                contracts.validate_contract(self.profile(rules=[{**rule, **change}]))
        for field in rule:
            candidate = dict(rule)
            del candidate[field]
            with self.subTest(missing=field), self.assertRaises(ValueError):
                contracts.validate_contract(self.profile(rules=[candidate]))
        for rules in (None, {}, [None]):
            with self.subTest(rules=rules), self.assertRaises(ValueError):
                contracts.validate_contract(self.profile(rules=rules))

    def test_overlap_is_global_across_resource_names_but_adjacency_is_valid(self):
        first = {"resource": "first", "offset": 0, "length": 2, "expected_hex": "4142"}
        for offset in (0, 1):
            second = {"resource": "different", "offset": offset, "length": 1, "expected_hex": "41"}
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                contracts.validate_contract(self.profile(rules=[first, second]))
        second = {"resource": "second", "offset": 2, "length": 2, "expected_hex": "4344"}
        self.assertTrue(contracts.check_contract(self.profile(rules=[second, first]), self.artifact)["ok"])

    def test_rule_count_and_total_byte_budgets_are_enforced(self):
        rules = [{"resource": "byte", "offset": index, "length": 1, "expected_hex": "00"} for index in range(1025)]
        with self.assertRaises(ValueError):
            contracts.validate_contract(self.profile(rules=rules))
        self.assertTrue(contracts.validate_contract(self.profile(rules=rules[:-1]))["ok"])
        large = [{"resource": "block", "offset": index * 1048576, "length": 1048576,
                  "expected_hex": "00" * 1048576} for index in range(9)]
        with self.assertRaises(ValueError):
            contracts.validate_contract(self.profile(rules=large))
        self.assertTrue(contracts.validate_contract(self.profile(rules=large[:-1]))["ok"])

    def test_provenance_must_be_finite_bounded_json_without_coercions(self):
        cycle = []
        cycle.append(cycle)
        deep = None
        for _ in range(70):
            deep = [deep]
        for value in (float("nan"), float("inf"), {"x": float("-inf")}, {1: "not a JSON key"},
                      b"bytes", ("tuple",), {"set"}, cycle, deep):
            with self.subTest(kind=type(value).__name__), self.assertRaises(ValueError):
                contracts.validate_contract(self.profile(provenance=value))
        with self.assertRaises(ValueError):
            contracts.validate_contract(self.profile(provenance="x" * (8 * 1024 * 1024)))

    def test_schema_rejects_non_json_containers_before_normalization(self):
        class JsonLikeDict(dict):
            pass

        profile = self.profile()
        profile["rules"][0] = JsonLikeDict(profile["rules"][0])
        with self.assertRaises(ValueError):
            contracts.validate_contract(profile)

    def test_revision_list_respects_json_node_budget(self):
        profile = self.profile(accepted_sha256=[f"{index:064x}" for index in range(100001)])
        with self.assertRaises(ValueError):
            contracts.validate_contract(profile)

    def test_identity_only_profile_has_no_rule_coverage(self):
        result = contracts.check_contract(self.profile(rules=[]), self.artifact)
        self.assertTrue(result["ok"])
        self.assertEqual(result["rule_count"], 0)
        self.assertEqual(result["coverage"], "identity_only")
        self.assertFalse(result["write_authorized"])

    def test_wrong_revision_never_reads_rule_offsets(self):
        profile = self.profile(rules=[{"resource": "untrusted", "offset": 10 ** 30, "length": 1, "expected_hex": "41"}])
        self.artifact.write_bytes(b"ABCE")
        with patch.object(contracts, "_read_rule", side_effect=AssertionError("must not read a rule after revision mismatch")):
            result = contracts.check_contract(profile, self.artifact)
        self.assertFalse(result["ok"])
        self.assertFalse(result["revision_match"])
        self.assertEqual(result["error_code"], "REVISION_MISMATCH")

    def test_out_of_bounds_and_wrong_bytes_are_measured_mismatches(self):
        for rule, code in (({"resource": "end", "offset": 3, "length": 2, "expected_hex": "4445"}, "RULE_OUT_OF_BOUNDS"),
                           ({"resource": "text", "offset": 1, "length": 2, "expected_hex": "0000"}, "RULE_MISMATCH")):
            with self.subTest(code=code):
                result = contracts.check_contract(self.profile(rules=[rule]), self.artifact)
                self.assertFalse(result["ok"])
                self.assertTrue(result["revision_match"])
                self.assertEqual(result["error_code"], code)
                self.assertFalse(result["write_authorized"])

    def test_resource_labels_are_inert_and_only_the_artifact_is_read(self):
        profile = self.profile()
        profile["rules"][0]["resource"] = "../../not-a-file"
        self.assertTrue(contracts.check_contract(profile, self.artifact)["ok"])
        self.assertEqual(list(self.root.iterdir()), [self.artifact])

    def test_mutation_after_hash_blocks_even_with_a_matching_initial_revision(self):
        hash_stream = contracts._hash_stream
        def mutate(stream):
            digest = hash_stream(stream)
            self.artifact.write_bytes(b"ABCE")
            return digest
        with patch.object(contracts, "_hash_stream", side_effect=mutate):
            result = contracts.check_contract(self.profile(), self.artifact)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "ARTIFACT_CHANGED")
        self.assertEqual(self.artifact.read_bytes(), b"ABCE")

    def test_same_size_mutation_after_rule_read_is_detected_even_with_restored_mtime(self):
        read_rule = contracts._read_rule
        original_stat = self.artifact.stat()
        def mutate(stream, rule):
            result = read_rule(stream, rule)
            self.artifact.write_bytes(b"ABCE")
            os.utime(self.artifact, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
            return result
        with patch.object(contracts, "_read_rule", side_effect=mutate):
            result = contracts.check_contract(self.profile(), self.artifact)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "ARTIFACT_CHANGED")
        self.assertFalse(result["write_authorized"])

    def test_artifact_hash_reads_are_streamed(self):
        self.artifact.write_bytes(b"A" * (3 * 1024 * 1024 + 17))
        profile = self.profile(accepted_sha256=[hashlib.sha256(self.artifact.read_bytes()).hexdigest()], rules=[])
        with patch.object(Path, "read_bytes", side_effect=AssertionError("artifact must be streamed")):
            self.assertTrue(contracts.check_contract(profile, self.artifact)["ok"])

    def test_change_during_an_actual_hash_read_blocks(self):
        payload = b"A" * (2 * 1024 * 1024)
        self.artifact.write_bytes(payload)
        profile = self.profile(accepted_sha256=[hashlib.sha256(payload).hexdigest()], rules=[])
        original_open = Path.open
        path = self.artifact
        prior = path.stat()

        class ChangingReader:
            def __init__(self, stream):
                self.stream, self.changed = stream, False

            def __enter__(self):
                return self

            def __exit__(self, *args):
                self.stream.close()

            def __getattr__(self, name):
                return getattr(self.stream, name)

            def read(self, length):
                self_chunk = self.stream.read(length)
                if self_chunk and not self.changed:
                    self.changed = True
                    with original_open(path, "r+b", buffering=0) as writer:
                        writer.seek(-1, os.SEEK_END)
                        writer.write(b"B")
                    os.utime(path, ns=(prior.st_atime_ns, prior.st_mtime_ns + 1000000))
                return self_chunk

        def open_with_mutation(candidate, *args, **kwargs):
            stream = original_open(candidate, *args, **kwargs)
            return ChangingReader(stream) if candidate == path else stream

        with patch.object(Path, "open", open_with_mutation):
            result = contracts.check_contract(profile, path)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "ARTIFACT_CHANGED")
        self.assertEqual(path.read_bytes(), payload[:-1] + b"B")


class LegacyImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="romancer legacy fixture ")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "historical profile.json"

    def test_import_preserves_data_and_hash_without_promoting_historical_claims(self):
        original = {"schema_version": 1, "status": "verified", "notes": "historical only", "offset": 21396}
        raw = json.dumps(original, indent=2).encode("utf-8")
        self.path.write_bytes(raw)
        result = contracts.import_legacy_profile(self.path)
        self.assertTrue(result["ok"])
        self.assertEqual(result["schema_version"], 2)
        self.assertEqual(result["status"], "HISTORICAL_UNVERIFIED")
        self.assertEqual(result["source_path"], str(self.path.resolve()))
        self.assertEqual(result["source_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(result["original_json"], original)
        self.assertFalse(result["write_authorized"])
        self.assertEqual(self.path.read_bytes(), raw)
        self.assertNotIn("accepted_sha256", result)

    def test_bundled_and_generated_shadowrun_profiles_remain_byte_identical(self):
        from romancer.v31 import shadowrun_scd_profile
        root = Path(__file__).resolve().parents[1]
        shadowrun_scd_profile(str(self.path))
        for path in (self.path,):
            with self.subTest(profile=path.name):
                before = path.read_bytes()
                result = contracts.import_legacy_profile(path)
                self.assertEqual(result["original_json"], json.loads(before))
                self.assertEqual(result["source_sha256"], hashlib.sha256(before).hexdigest())
                self.assertEqual(result["status"], "HISTORICAL_UNVERIFIED")
                self.assertEqual(path.read_bytes(), before)

    def test_import_rejects_duplicate_keys_nonfinite_and_invalid_json(self):
        for text in ('{"a": 1, "a": 2}', '{"nested": {"a": 1, "a": 2}}', '{"a": NaN}',
                     '{"a": Infinity}', '{"a": 1e999}', '{', '[]'):
            self.path.write_text(text, encoding="utf-8")
            with self.subTest(text=text), self.assertRaises(ValueError):
                contracts.import_legacy_profile(self.path)

    def test_import_is_bounded_to_eight_mib(self):
        self.path.write_bytes(b'{"note":"' + b"x" * (8 * 1024 * 1024) + b'"}')
        with self.assertRaises(ValueError):
            contracts.import_legacy_profile(self.path)

    def test_bounded_contract_loader_rejects_duplicate_keys(self):
        self.path.write_text('{"schema_version": 2, "schema_version": 2}', encoding="utf-8")
        with self.assertRaises(ValueError):
            contracts.load_contract(self.path)


if __name__ == "__main__":
    unittest.main()
