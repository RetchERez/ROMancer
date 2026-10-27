import unittest

class DebuggerFailureTests(unittest.TestCase):
    def test_actual_windows_crashes_are_not_misdiagnosed_as_cpu_incompatibility(self):
        from romancer.debugger_failures import process_failure
        for code in (3221226356,3221225477,-1073741819):
            error=process_failure('Genesis observer',code,'')
            self.assertEqual(error.code,'NATIVE_CRASH');self.assertNotIn('CPU',str(error));self.assertIn('support',str(error).lower())
    def test_illegal_instruction_dependency_script_and_unclassified_exit_have_distinct_remedies(self):
        from romancer.debugger_failures import process_failure
        self.assertEqual(process_failure('Observer',0xc000001d,'').code,'ILLEGAL_INSTRUCTION')
        self.assertEqual(process_failure('Observer',0xc0000135,'').code,'MISSING_DEPENDENCY')
        e=process_failure('Observer',1,'[LUA ERROR] X:/private/file.lua: invalid token')
        self.assertEqual(e.code,'CAPTURE_SCRIPT_ERROR');self.assertNotIn('private',str(e))
        e=process_failure('Observer',7,'unrecognized details');self.assertEqual(e.code,'NATIVE_EXIT');self.assertIn('7',str(e));self.assertNotIn('CPU',str(e))
