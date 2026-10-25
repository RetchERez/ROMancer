import json
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest

from romancer.bisect_v10 import _run_oracle
from romancer.repair_v10 import parameter_repair
from romancer.v10 import _test_cli_bisect, _test_repair


class OracleExecutionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="romancer oracle spaces ")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.rom = self.root / "candidate ROM.bin"
        self.script = self.root / "defect oracle.py"
        self.script.write_text(
            "import json, sys\n"
            "from pathlib import Path\n"
            "data = Path(sys.argv[1]).read_bytes()\n"
            "print(json.dumps(sys.argv[1:]))\n"
            "print('oracle diagnostic', file=sys.stderr)\n"
            "sys.exit({b'good': 0, b'defect': 1}.get(data, 7))\n",
            encoding="utf-8",
        )

    def test_argv_preserves_rom_path_and_exit_contract(self):
        command = [sys.executable, str(self.script), "{rom}"]
        for payload, expected_bad, expected_code in (
            (b"good", False, 0), (b"defect", True, 1)
        ):
            with self.subTest(payload=payload):
                self.rom.write_bytes(payload)
                bad, detail = _run_oracle(command, self.rom)
                self.assertEqual(bad, expected_bad)
                self.assertEqual(detail["returncode"], expected_code)
                self.assertEqual(detail["command"][-1], str(self.rom))
                self.assertEqual(json.loads(detail["stdout"]), [str(self.rom)])
                self.assertIn("oracle diagnostic", detail["stderr"])
        self.assertEqual(command, [sys.executable, str(self.script), "{rom}"])

    def test_string_tokenizes_before_replacing_unquoted_rom(self):
        self.rom.write_bytes(b"defect")
        command = shlex.join([sys.executable, str(self.script)]) + " {rom}"
        bad, detail = _run_oracle(command, self.rom)
        self.assertTrue(bad)
        self.assertEqual(detail["command"], [sys.executable, str(self.script), str(self.rom)])
        self.assertEqual(json.loads(detail["stdout"]), [str(self.rom)])

    def test_posix_quoted_template_preserves_literal_arguments(self):
        self.rom.write_bytes(b"good")
        literal = r"literal space & ; $HOME $(echo ignored) C:\a\b"
        command = shlex.join([
            sys.executable, str(self.script), "{rom}", literal, "--rom={rom}", ""
        ])
        bad, detail = _run_oracle(command, self.rom)
        self.assertFalse(bad)
        self.assertEqual(
            json.loads(detail["stdout"]),
            [str(self.rom), literal, "--rom=" + str(self.rom), ""],
        )

    def test_argv_bypasses_shell_and_tokenization(self):
        self.rom.write_bytes(b"good")
        literal = r"literal 'quote' & ; $HOME $(echo ignored) C:\a\b"
        bad, detail = _run_oracle(
            [sys.executable, str(self.script), "{rom}", literal, "--rom={rom}", ""],
            self.rom,
        )
        self.assertFalse(bad)
        self.assertEqual(
            json.loads(detail["stdout"]),
            [str(self.rom), literal, "--rom=" + str(self.rom), ""],
        )

    def test_invalid_exit_code_is_an_oracle_error(self):
        self.rom.write_bytes(b"invalid")
        argv = [sys.executable, str(self.script), "{rom}"]
        for command in (argv, shlex.join(argv)):
            with self.subTest(command=command):
                with self.assertRaisesRegex(RuntimeError, "oracle exit 7:.*oracle diagnostic"):
                    _run_oracle(command, self.rom)

    def test_timeout_is_not_a_defect_verdict(self):
        with self.assertRaises(subprocess.TimeoutExpired):
            _run_oracle([sys.executable, "-c", "import time; time.sleep(10)"], self.rom, timeout=1)

    def test_internal_bisection_oracle_in_directory_with_spaces(self):
        result = _test_cli_bisect(self.root)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["detail"]["selected"][0]["start"], 11)

    def test_internal_repair_oracle_in_directory_with_spaces(self):
        result = _test_repair(self.root)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["detail"]["status"], "verified_unique_candidate")
        self.assertEqual(result["detail"]["passing"], 1)

    def test_repair_preserves_pass_fail_and_oracle_error(self):
        self.rom.write_bytes(b"\x00")
        self.script.write_text(
            "import sys\n"
            "from pathlib import Path\n"
            "sys.exit(Path(sys.argv[1]).read_bytes()[0])\n",
            encoding="utf-8",
        )
        argv = [sys.executable, str(self.script), "{rom}"]
        for command in (argv, shlex.join(argv[:-1]) + " {rom}"):
            with self.subTest(command=command):
                result = parameter_repair(
                    str(self.rom), "0", "0,1,7", command,
                    out_dir=str(self.root / "repair candidates"),
                )
                self.assertEqual(result["status"], "verified_unique_candidate")
                self.assertEqual(result["passing_count"], 1)
                self.assertEqual(result["recommended"]["value_int"], 0)
                passed, failed, invalid = [item["oracle"] for item in result["candidates"]]
                self.assertTrue(passed["pass"])
                self.assertTrue(failed["ok"])
                self.assertFalse(failed["pass"])
                self.assertFalse(invalid["ok"])
                self.assertTrue(invalid["oracle_error"])
                self.assertEqual(invalid["returncode"], 7)


if __name__ == "__main__":
    unittest.main()
