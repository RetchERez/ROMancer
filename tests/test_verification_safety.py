import hashlib
import io
import json
from pathlib import Path
import stat
import struct
import tempfile
import unittest
from unittest.mock import patch
import warnings
import zipfile
import zlib

from romancer.certify_v10 import certify
from romancer import v22_30 as lab


class VerificationSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="romancer verification ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def json_file(self, name, data):
        path = self.root / name
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def gate(self, **changes):
        gate = {"name": "fixture", "kind": "json", "path": "assertion.json", "required": True}
        gate.update(changes)
        return gate

    def evaluate(self, gates):
        self.json_file("assertion.json", {"ok": True})
        return certify(str(self.json_file("manifest.json", {"gates": gates})))

    def package(self, entries):
        path = self.root / "package.zip"
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for name, data in entries:
                    if isinstance(name, str):
                        info = zipfile.ZipInfo(name)
                        # Preserve adversarial names that Windows ZipInfo normalizes.
                        info.filename = name
                        info.compress_type = zipfile.ZIP_DEFLATED
                        name = info
                    archive.writestr(name, data)
        return path

    def test_existing_fake_executable_is_discovery_only(self):
        exe = self.root / "fake.exe"
        exe.write_bytes(b"This is not an emulator")
        config = self.json_file("bridge.json", {"backends": [{"name": "mgba", "path": str(exe)}]})
        result = lab.bridge_probe(str(config))
        row = result["backends"][0]
        self.assertFalse(row["live_control"])
        self.assertTrue(row["path_exists"])
        self.assertTrue(row["executable_discovered"])
        self.assertFalse(result["live_control"])
        self.assertEqual(row["handshake_status"], "NOT_RUN")
        self.assertEqual(result["scope"], "executable_discovery")

    def test_bridge_directory_is_not_executable_discovery(self):
        config = self.json_file("bridge.json", {"backends": [{"name": "mgba", "path": str(self.root)}]})
        row = lab.bridge_probe(str(config))["backends"][0]
        self.assertFalse(row.get("executable_discovered", row["path_exists"]))

    def test_bridge_malformed_config_is_non_success(self):
        for data in ([], {"backends": "bad"}, {"backends": [None]}):
            with self.subTest(data=data):
                self.assertFalse(lab.bridge_probe(str(self.json_file("bridge.json", data)))["ok"])

    def test_empty_all_optional_and_duplicate_manifests_are_blocked(self):
        for gates in ([], [self.gate(required=False)], [self.gate(), self.gate()],
                      [self.gate(), self.gate(name=" Fixture ")]):
            with self.subTest(gates=gates):
                self.assertFalse(self.evaluate(gates)["ok"])

    def test_malformed_manifests_return_non_success(self):
        for data in ({}, [], {"gates": {}}, {"gates": "bad"}, {"gates": [None]},
                     {"gates": [self.gate(name="")]}, {"gates": [self.gate(path=3)]}):
            with self.subTest(data=data):
                self.assertFalse(certify(str(self.json_file("manifest.json", data)))["ok"])
        path = self.root / "manifest.json"
        for text in ('{', '{"gates": [], "gates": []}', '{"gates": NaN}'):
            path.write_text(text, encoding="utf-8")
            self.assertFalse(certify(str(path))["ok"])
        self.assertFalse(certify(str(self.root / "missing-manifest.json"))["ok"])

    def test_required_is_a_strict_boolean(self):
        for value in ("false", "true", 0, 1, None, [], {}):
            with self.subTest(value=value):
                self.assertFalse(self.evaluate([self.gate(required=value)])["ok"])

    def test_unsupported_and_missing_even_optional_gates_block(self):
        for changes in ({"kind": "magic"}, {"path": "missing.json"},
                        {"kind": "ledger", "path": "missing.json"},
                        {"kind": "coverage", "path": "missing.json"},
                        {"kind": "hash", "path": "missing.json", "expected": "0" * 64}):
            for required in (True, False):
                with self.subTest(changes=changes, required=required):
                    result = self.evaluate([self.gate(), self.gate(name="other", required=required, **changes)])
                    self.assertFalse(result["ok"])

    def test_imported_json_is_labeled_and_never_certified(self):
        result = self.evaluate([self.gate()])
        self.assertTrue(result["ok"])
        self.assertEqual(result["release_status"], "GATES_PASSED")
        self.assertEqual(result["scope"], {"required_gates": ["fixture"]})
        self.assertEqual(result["gates"][0]["provenance"], "imported_assertion")
        self.assertFalse(result["gates"][0]["measured"])

    def test_successful_child_reports_import_as_scoped_assertions(self):
        self.json_file("assertion.json", {"ok": True})
        child = self.json_file("child.json", {"gates": [self.gate()]})
        demo = self.json_file("demo.json", {"gates": {"menu": "verified"}})
        for producer, manifest in ((certify, child), (lab.demo_certify, demo)):
            with self.subTest(producer=producer.__name__):
                report = self.root / "child-result.json"
                child_result = producer(str(manifest), str(report))
                self.assertTrue(child_result["ok"])
                parent = self.json_file("parent.json", {"gates": [self.gate(name="parent", path=report.name)]})
                result = certify(str(parent))
                self.assertTrue(result["ok"])
                row = result["gates"][0]
                self.assertEqual(row["provenance"], "imported_assertion")
                self.assertFalse(row["measured"])
                self.assertEqual(row["asserted_status"], "GATES_PASSED")
                self.assertEqual(row["asserted_scope"], child_result["scope"])
                self.assertEqual(result["scope"], {"required_gates": ["parent"]})

    def test_assertion_booleans_and_conflicting_statuses_are_rejected(self):
        manifest = self.json_file("manifest.json", {"gates": [self.gate()]})
        for obj in ({"ok": "false"}, {"pass": 1}, {"ok": []}, {"ok": True, "pass": False},
                    {"ok": True, "status": "FAIL"}, {"ok": True, "status": "banana"},
                    {"status": 1}, {"ok": False, "status": "GATES_PASSED"},
                    {"ok": True, "status": "GATES_PASSED", "gate_status": "FAIL"}, {}, []):
            with self.subTest(obj=obj):
                self.json_file("assertion.json", obj)
                self.assertFalse(certify(str(manifest))["ok"])

    def test_fail_blocked_and_not_run_remain_distinct(self):
        manifest = self.json_file("manifest.json", {"gates": [self.gate()]})
        for status in ("FAIL", "BLOCKED", "NOT_RUN"):
            with self.subTest(status=status):
                self.json_file("assertion.json", {"status": status})
                result = certify(str(manifest))
                self.assertFalse(result["ok"])
                self.assertEqual(result["gates"][0]["gate_status"], status)

    def test_hash_gate_measures_only_artifact_digest(self):
        data = b"synthetic fixture"
        (self.root / "fixture.txt").write_bytes(data)
        gate = self.gate(kind="hash", path="fixture.txt", expected=hashlib.sha256(data).hexdigest())
        result = self.evaluate([gate])
        self.assertTrue(result["ok"])
        self.assertEqual(result["release_status"], "GATES_PASSED")
        self.assertEqual(result["gates"][0]["provenance"], "measured_hash")
        self.assertTrue(result["gates"][0]["measured"])
        (self.root / "fixture.txt").write_bytes(b"changed")
        result = self.evaluate([gate])
        self.assertFalse(result["ok"])
        self.assertEqual(result["gates"][0]["gate_status"], "FAIL")

    def test_empty_coverage_and_invalid_thresholds_cannot_pass(self):
        self.json_file("coverage.json", {})
        self.assertFalse(self.evaluate([self.gate(kind="coverage", path="coverage.json")])["ok"])
        self.json_file("coverage.json", {"categories": {"fixture": {"known": ["a"], "hit": ["a"]}}})
        for minimum in (-1, 101, True, "95", float("nan")):
            with self.subTest(minimum=minimum):
                self.assertFalse(self.evaluate([self.gate(kind="coverage", path="coverage.json", minimum=minimum)])["ok"])

    def test_coverage_keeps_legacy_numeric_ids_and_labels_imports(self):
        self.json_file("coverage.json", {"categories": {"maps": {"known": [1, 2, 3], "hit": [1, 2, 3]}}})
        result = self.evaluate([self.gate(kind="coverage", path="coverage.json")])
        self.assertTrue(result["ok"])
        self.assertEqual(result["gates"][0]["input_provenance"], "imported_assertion")

    def test_coverage_rounding_does_not_turn_incomplete_into_pass(self):
        known = [str(i) for i in range(20001)]
        self.json_file("coverage.json", {"categories": {"maps": {"known": known, "hit": known[:-1]}}})
        result = self.evaluate([self.gate(kind="coverage", path="coverage.json", minimum=100)])
        self.assertFalse(result["ok"])
        self.assertEqual(result["gates"][0]["gate_status"], "FAIL")

    def test_ledger_checks_actual_overlap_and_rejects_malformed_ranges(self):
        for allocations, expected in (([{"start": 0, "end": 3}, {"start": 4, "end": 7}], True),
                                      ([{"start": 0, "end": 3}, {"start": 3, "end": 7}], False),
                                      ([{"start": 4, "end": 3}], False),
                                      ([{"start": True, "end": 3}], False)):
            with self.subTest(allocations=allocations):
                self.json_file("ledger.json", {"allocations": allocations})
                result = self.evaluate([self.gate(kind="ledger", path="ledger.json")])
                self.assertEqual(result["ok"], expected)
                if expected:
                    self.assertEqual(result["gates"][0]["provenance"], "executed_validator")

    def test_valid_optional_failure_does_not_enlarge_required_scope(self):
        self.json_file("optional.json", {"ok": False})
        result = self.evaluate([self.gate(), self.gate(name="optional", required=False, path="optional.json")])
        self.assertTrue(result["ok"])
        self.assertEqual(result["scope"], {"required_gates": ["fixture"]})
        self.assertEqual(result["gates"][1]["gate_status"], "FAIL")

    def test_demo_gate_assertions_have_declared_scope(self):
        path = self.json_file("demo.json", {"gates": {"menu": "verified", "battle": "PASS"}})
        result = lab.demo_certify(str(path))
        self.assertTrue(result["ok"])
        self.assertEqual(result["release_status"], "GATES_PASSED")
        self.assertTrue(all(row["provenance"] == "imported_assertion" for row in result["gates"]))

    def test_demo_invalid_scope_cannot_pass(self):
        for gates in ([], [{"name": "a", "status": "PASS", "required": False}],
                      [{"name": "a", "status": "PASS", "required": "false"}],
                      [{"name": "a", "status": "PASS"}] * 2,
                      [{"name": "a", "status": "PASS", "kind": "magic"}]):
            with self.subTest(gates=gates):
                self.assertFalse(lab.demo_certify(str(self.json_file("demo.json", {"gates": gates})))["ok"])

    def test_empty_packages_do_not_pass(self):
        directory = self.root / "empty"
        directory.mkdir()
        self.assertFalse(lab.release_boundary_scan(str(directory))["ok"])
        for entries in ([], [("docs/", b"")]):
            path = self.package(entries)
            self.assertFalse(lab.release_boundary_scan(str(path))["ok"])

    def test_unknown_forbidden_nested_and_private_members_block(self):
        for name in ("game.bin", "payload.dat", "nested.zip", "nested.tar.gz", "reports/private.json"):
            with self.subTest(name=name):
                result = lab.release_boundary_scan(str(self.package([("README.md", b"fixture"), (name, b"payload")])))
                self.assertFalse(result["ok"])

    def test_tool_source_roles_are_packaging_only(self):
        application = Path(__file__).resolve().parents[1]
        roles = (("run.ps1", "run.ps1"),
                 ("tests/mock_libretro.c", "tests/mock_libretro.c"),
                 ("examples/v21/sample_retroarch_fixture.cht", "examples/v21/sample_retroarch_fixture.cht"),
                 ("examples/traces/synthetic.log", "examples/fake_trace.log"))
        for index, (member, source) in enumerate(roles):
            data = (application / source).read_bytes()
            directory = self.root / f"source-role-{index}"
            staged = directory / member
            staged.parent.mkdir(parents=True)
            staged.write_bytes(data)
            for path in (application / source, directory, self.package([(member, data)])):
                with self.subTest(member=member, path=path):
                    result = lab.certify_release(str(path))
                    self.assertTrue(result["ok"])
                    self.assertEqual(result["release_status"], "PACKAGE_CHECK_PASSED")
                    self.assertEqual(result["scope"], "package_policy")
                    self.assertFalse(result["content_safety_verified"])

    def test_local_only_directories_are_excluded_even_with_allowed_files(self):
        names = ("work_private", ".git", "__pycache__", ".superpowers", ".venv", "dist", "reports")
        for index, name in enumerate(names):
            member = f"project/{name.upper()}/fixture.txt"
            directory = self.root / f"excluded-role-{index}"
            staged = directory / member
            staged.parent.mkdir(parents=True)
            staged.write_bytes(b"synthetic local-only fixture")
            for path in (directory, self.package([("README.md", b"fixture"), (member, b"fixture")])):
                with self.subTest(name=name, path=path):
                    result = lab.release_boundary_scan(str(path))
                    self.assertFalse(result["ok"])
                    self.assertEqual(result["release_status"], "BLOCKED")

    def test_empty_excluded_directory_does_not_hide_in_valid_package(self):
        for index, name in enumerate(("work_private", ".git", "__pycache__", ".superpowers", ".venv", "dist", "reports")):
            directory = self.root / f"empty-excluded-{index}"
            (directory / name).mkdir(parents=True)
            (directory / "README.md").write_bytes(b"fixture")
            for path in (directory, self.package([("README.md", b"fixture"), (name + "/", b"")])):
                with self.subTest(name=name, path=path):
                    self.assertFalse(lab.release_boundary_scan(str(path))["ok"])

    def test_tool_source_suffixes_do_not_approve_private_reports(self):
        for suffix in ("ps1", "c", "log", "cht"):
            with self.subTest(suffix=suffix):
                package = self.package([("README.md", b"fixture"), (f"reports/private.{suffix}", b"fixture")])
                result = lab.certify_release(str(package))
                self.assertFalse(result["ok"])
                self.assertFalse(result["content_safety_verified"])

    def test_duplicate_and_unsafe_archive_paths_block(self):
        for name in ("README.md", "readme.MD", "../escape.txt", "/absolute.txt", "C:/drive.txt",
                     "a\\b.txt", "a//b.txt", "a/./b.txt", "a/../b.txt", "a.txt:stream.txt",
                     "CON.txt", "dir./a.txt", "dir /a.txt", "COM\u00b9.txt", "LPT\u00b2.txt", "COM\u00b3/child.txt"):
            with self.subTest(name=name):
                self.assertFalse(lab.release_boundary_scan(str(self.package([("README.md", b"ok"), (name, b"x")])))["ok"])

    def test_archive_symlink_and_file_parent_conflict_block(self):
        link = zipfile.ZipInfo("link.txt")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        for entries in ([(link, b"target")], [("dir.txt", b"x"), ("dir.txt/child.md", b"x")]):
            self.assertFalse(lab.release_boundary_scan(str(self.package(entries)))["ok"])

    def test_nested_archive_signature_is_rejected_even_with_allowed_suffix(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("inside.txt", b"fixture")
        self.assertFalse(lab.release_boundary_scan(str(self.package([("disguised.txt", buffer.getvalue())])))["ok"])

    def test_prefixed_nested_zip_is_rejected_without_extraction(self):
        inner = io.BytesIO(b"Synthetic prefix\n")
        inner.seek(0, 2)
        with zipfile.ZipFile(inner, "w") as archive:
            archive.writestr("../escape.txt", b"synthetic")
            archive.comment = b"x" * 65535
        self.assertTrue(zipfile.is_zipfile(io.BytesIO(inner.getvalue())))
        path = self.package([("notes.txt", inner.getvalue())])
        self.assertFalse(lab.release_boundary_scan(str(path))["ok"])

    def test_forged_uncompressed_zip_size_cannot_truncate_validation(self):
        for budget in (10, 20000):
            with self.subTest(budget=budget):
                path = self.package([("a.txt", b"A" * 10000)])
                raw = bytearray(path.read_bytes())
                central = raw.index(b"PK\x01\x02")
                crc = zlib.crc32(b"A")
                for offset, value in ((14, crc), (22, 1), (central + 16, crc), (central + 24, 1)):
                    struct.pack_into("<I", raw, offset, value)
                path.write_bytes(raw)
                with patch.object(lab, "PACKAGE_MAX_MEMBER_BYTES", budget), patch.object(lab, "PACKAGE_MAX_TOTAL_BYTES", budget):
                    self.assertFalse(lab.release_boundary_scan(str(path))["ok"])

    def test_deflate_requires_eof_and_rejects_unused_compressed_bytes(self):
        payload = b"synthetic fixture" * 100
        compressor = zlib.compressobj(wbits=-15)
        encoded = compressor.compress(payload) + compressor.flush()
        for encoded_member in (encoded[:-1], encoded + b"unclassified", encoded + encoded):
            with self.subTest(encoded_size=len(encoded_member)):
                name = b"a.txt"
                crc = zlib.crc32(payload)
                local = struct.pack("<4s5H3I2H", b"PK\x03\x04", 20, 0, 8, 0, 0,
                                    crc, len(encoded_member), len(payload), len(name), 0) + name + encoded_member
                central = struct.pack("<4s6H3I5H2I", b"PK\x01\x02", 20, 20, 0, 8, 0, 0,
                                      crc, len(encoded_member), len(payload), len(name), 0, 0, 0, 0, 0, 0) + name
                end = struct.pack("<4s4H2IH", b"PK\x05\x06", 0, 0, 1, 1, len(central), len(local), 0)
                path = self.root / "malformed-deflate.zip"
                path.write_bytes(local + central + end)
                self.assertFalse(lab.release_boundary_scan(str(path))["ok"])

    def test_valid_stored_and_descriptor_archives_still_pass(self):
        class Unseekable(io.BytesIO):
            def seek(self, *args):
                raise io.UnsupportedOperation("synthetic nonseekable output")

        payload = b"synthetic fixture" * 10000
        for method in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            with self.subTest(method=method):
                buffer = Unseekable()
                with zipfile.ZipFile(buffer, "w", compression=method) as archive:
                    archive.writestr("a.txt", payload)
                path = self.root / "descriptor.zip"
                path.write_bytes(buffer.getvalue())
                result = lab.release_boundary_scan(str(path))
                self.assertTrue(result["ok"])
                self.assertEqual(result["total_uncompressed_bytes"], len(payload))

    def test_malformed_and_crc_corrupt_archives_block(self):
        path = self.root / "broken.zip"
        path.write_bytes(b"not a zip")
        self.assertFalse(lab.release_boundary_scan(str(path))["ok"])
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
            archive.writestr("fixture.txt", b"unique payload")
        path.write_bytes(path.read_bytes().replace(b"unique payload", b"broken payload"))
        self.assertFalse(lab.release_boundary_scan(str(path))["ok"])

    def test_package_budgets_fail_closed(self):
        path = self.package([("a.txt", b"12345"), ("b.txt", b"12345")])
        for constant, limit in (("PACKAGE_MAX_ENTRIES", 1), ("PACKAGE_MAX_MEMBER_BYTES", 4),
                                ("PACKAGE_MAX_TOTAL_BYTES", 9), ("PACKAGE_MAX_ARCHIVE_BYTES", 10)):
            with self.subTest(constant=constant), patch.object(lab, constant, limit, create=True):
                self.assertFalse(lab.release_boundary_scan(str(path))["ok"])

    def test_zip_metadata_budget_is_checked_before_loading_entries(self):
        path = self.package([("a.txt", b"x")])
        with patch.object(lab, "PACKAGE_MAX_DIRECTORY_BYTES", 1, create=True):
            self.assertFalse(lab.release_boundary_scan(str(path))["ok"])

    def test_malformed_directory_header_is_not_skipped(self):
        path = self.package([("docs/", b""), ("docs/a.txt", b"x")])
        raw = bytearray(path.read_bytes())
        raw[0:4] = b"BAD!"
        path.write_bytes(raw)
        self.assertFalse(lab.release_boundary_scan(str(path))["ok"])

    def test_multidisk_and_trailing_payload_archives_are_blocked(self):
        for corruption in ("disk", "trailing"):
            with self.subTest(corruption=corruption):
                path = self.package([("a.txt", b"x")])
                raw = bytearray(path.read_bytes())
                if corruption == "disk":
                    offset = raw.rfind(b"PK\x05\x06")
                    struct.pack_into("<H", raw, offset + 4, 1)
                else:
                    raw.extend(b"unclassified trailing payload")
                path.write_bytes(raw)
                self.assertFalse(lab.release_boundary_scan(str(path))["ok"])

    def test_archive_with_forbidden_outer_suffix_is_blocked(self):
        path = self.package([("a.txt", b"x")])
        target = self.root / "game.bin"
        path.rename(target)
        self.assertFalse(lab.release_boundary_scan(str(target))["ok"])

    def test_manifest_status_and_demo_artifact_are_not_ignored(self):
        self.assertFalse(self.evaluate([self.gate(status="FAIL")])["ok"])
        path = self.json_file("demo.json", {"gates": [{"name": "missing", "kind": "json", "path": "missing.json", "status": "PASS"}]})
        self.assertFalse(lab.demo_certify(str(path))["ok"])

    def test_permitted_packages_are_only_packaging_success(self):
        directory = self.root / "source"
        directory.mkdir()
        (directory / "README.md").write_text("Synthetic fixture", encoding="utf-8")
        (directory / "fixture.py").write_text("print('synthetic fixture')", encoding="utf-8")
        paths = (directory, directory / "README.md", directory / "fixture.py",
                 self.package([("docs/", b""), ("docs/README.md", b"Synthetic fixture"), ("fixture.py", b"pass")]))
        for path in paths:
            with self.subTest(path=path):
                result = lab.certify_release(str(path))
                self.assertTrue(result["ok"])
                self.assertEqual(result["release_status"], "PACKAGE_CHECK_PASSED")
                self.assertEqual(result["scope"], "package_policy")
                self.assertFalse(result["content_safety_verified"])
                self.assertEqual(result["boundary_scan"]["release_status"], "PACKAGE_CHECK_PASSED")


if __name__ == "__main__":
    unittest.main()
