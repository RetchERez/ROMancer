import json
from pathlib import Path
import shlex
import sys
import tempfile
import unittest

from romancer.qa_lab_v14 import qa_run
from romancer.v14 import v14_self_test


class QAExecutionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="romancer QA spaces ")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.data = self.root / "input bytes.bin"
        self.data.write_bytes(b"synthetic QA input")
        self.script = self.root / "QA child.py"
        self.script.write_text(
            "import json, sys\n"
            "from pathlib import Path\n"
            "assert Path(sys.argv[1]).read_bytes() == b'synthetic QA input'\n"
            "print(json.dumps(sys.argv[1:]))\n"
            "print('QA child ran', file=sys.stderr)\n"
            "sys.exit(int(sys.argv[2]))\n",
            encoding="utf-8",
        )

    def run_tasks(self, tasks):
        manifest = self.root / "QA manifest.json"
        manifest.write_text(json.dumps({"tasks": tasks}), encoding="utf-8")
        return qa_run(str(manifest), workers=2)

    def command(self, exit_code=0):
        return [sys.executable, str(self.script), str(self.data), str(exit_code)]

    def test_internal_qa_self_test_executes_both_jobs(self):
        result = v14_self_test()
        check = next(t for t in result["tests"] if t["name"] == "parallel QA runner")
        self.assertTrue(check["ok"], result)

    def test_parallel_argv_jobs_preserve_paths_and_literal_arguments(self):
        literal = r"space 'quote' & ; $HOME $(echo ignored) C:\a\b"
        command = self.command() + [literal, ""]
        result = self.run_tasks([
            {"id": "b", "command": command},
            {"id": "a", "command": command},
        ])
        self.assertTrue(result["ok"], result)
        self.assertEqual((result["task_count"], result["passed"], result["failed"]), (2, 2, 0))
        self.assertEqual([r["id"] for r in result["results"]], ["a", "b"])
        for child in result["results"]:
            self.assertEqual(json.loads(child["stdout"]), [str(self.data), "0", literal, ""])
            self.assertEqual(child["returncode"], 0)
            self.assertIn("QA child ran", child["stderr"])

    def test_exit_codes_are_compared_to_declared_expectations(self):
        result = self.run_tasks([
            {"id": "a", "command": self.command(0)},
            {"id": "b", "command": self.command(1)},
            {"id": "c", "command": self.command(7), "expected_exit": 7},
            {"id": "d", "command": self.command(0), "expected_exit": 1},
        ])
        self.assertFalse(result["ok"], result)
        self.assertEqual((result["passed"], result["failed"]), (2, 2))
        self.assertEqual([r["returncode"] for r in result["results"]], [0, 1, 7, 0])
        self.assertEqual([r["ok"] for r in result["results"]], [True, False, True, False])

    def test_posix_string_commands_remain_supported(self):
        literal = r"space & ; 'quote' C:\a\b"
        result = self.run_tasks([
            {"id": "string", "command": shlex.join(self.command() + [literal, ""])},
        ])
        self.assertTrue(result["ok"], result)
        self.assertEqual(
            json.loads(result["results"][0]["stdout"]),
            [str(self.data), "0", literal, ""],
        )

    def test_object_command_is_rejected_without_executing_its_keys(self):
        marker = self.root / "object child executed.txt"
        script = self.root / "marker child.py"
        script.write_text(
            "import sys\nfrom pathlib import Path\n"
            "Path(sys.argv[1]).write_text('child executed', encoding='utf-8')\n",
            encoding="utf-8",
        )
        command = dict.fromkeys([sys.executable, str(script), str(marker)], "ignored")
        result = self.run_tasks([
            {"id": "invalid", "command": command},
            {"id": "working", "command": self.command()},
        ])
        self.assertFalse(marker.exists(), "JSON object keys were executed as argv")
        self.assertFalse(result["ok"], result)
        self.assertEqual((result["task_count"], result["passed"], result["failed"]), (2, 1, 1))
        error = next(r for r in result["results"] if "error" in r)
        self.assertIn("nonempty list of strings", error["error"])
        working = next(r for r in result["results"] if r.get("id") == "working")
        self.assertEqual(json.loads(working["stdout"]), [str(self.data), "0"])

    def test_invalid_argv_shapes_fail_validation_while_valid_jobs_continue(self):
        invalid_commands = [
            [], {}, None, True, 7, 1.5,
            self.command() + [None], self.command() + [False],
            self.command() + [7], self.command() + [1.5],
            self.command() + [[]], self.command() + [{}],
        ]
        for command in invalid_commands:
            with self.subTest(command=command):
                result = self.run_tasks([
                    {"id": "invalid", "command": command},
                    {"id": "working", "command": self.command()},
                ])
                self.assertFalse(result["ok"], result)
                self.assertEqual((result["task_count"], result["passed"], result["failed"]), (2, 1, 1))
                error = next(r for r in result["results"] if "error" in r)
                self.assertIn("nonempty list of strings", error["error"])
                working = next(r for r in result["results"] if r.get("id") == "working")
                self.assertEqual(json.loads(working["stdout"]), [str(self.data), "0"])

    def test_missing_executable_fails_without_losing_successful_job(self):
        result = self.run_tasks([
            {"id": "missing", "command": [str(self.root / "missing executable.exe")]},
            {"id": "working", "command": self.command()},
        ])
        self.assertFalse(result["ok"], result)
        self.assertEqual((result["task_count"], result["passed"], result["failed"]), (2, 1, 1))
        error = next(r for r in result["results"] if "error" in r)
        self.assertFalse(error["ok"])
        self.assertRegex(error["error"], "WinError 2|No such file or directory")
        working = next(r for r in result["results"] if r.get("id") == "working")
        self.assertEqual(working["returncode"], 0)

    def test_timeout_remains_a_failed_job(self):
        result = self.run_tasks([
            {"id": "timeout", "command": [sys.executable, "-c", "import time; time.sleep(10)"], "timeout": 1},
            {"id": "working", "command": self.command()},
        ])
        self.assertFalse(result["ok"], result)
        self.assertEqual((result["passed"], result["failed"]), (1, 1))
        error = next(r for r in result["results"] if "error" in r)
        self.assertIn("timed out", error["error"])


if __name__ == "__main__":
    unittest.main()
