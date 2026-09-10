"""API-specific creation flags; these contracts do not claim native execution."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent


def call_named(file, name):
    tree = ast.parse((ROOT / file).read_text(encoding='utf-8'))
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Attribute) and node.func.attr == name]
    if len(calls) != 1:
        raise AssertionError(f'expected exactly one {name} call')
    return calls[0]


def integer_flags(node):
    if isinstance(node, ast.Constant) and type(node.value) is int:
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return integer_flags(node.left) | integer_flags(node.right)
    raise AssertionError('creation flags must be an explicit integer bitmask')


class CreationFlagContracts(unittest.TestCase):
    def test_token_launch_does_not_conflict_with_implicit_new_console(self):
        call = call_named('Windows标准用户验收v22.py', 'CreateProcessWithLogonW')
        self.assertEqual(integer_flags(call.args[6]), 0x4 | 0x400)
        self.assertEqual(integer_flags(call.args[3]), 1)  # LOGON_WITH_PROFILE

    def test_user_profile_environment_is_not_inherited_from_admin(self):
        call = call_named('Windows标准用户验收v22.py', 'CreateProcessWithLogonW')
        self.assertIsInstance(call.args[7], ast.Constant)
        self.assertIsNone(call.args[7].value)

    def test_inner_app_still_uses_detached_console(self):
        call = call_named('Windows原生宿主v13.py', 'Popen')
        flags = next(k.value for k in call.keywords if k.arg == 'creationflags')
        self.assertEqual(integer_flags(flags), 0x8)

    def test_ownership_precedes_resume_and_security_is_not_bypassed(self):
        text = (ROOT / 'Windows标准用户验收v22.py').read_text(encoding='utf-8')
        start = text.index("api.CreateProcessWithLogonW(name, '.'")
        self.assertLess(text.index('api.AssignProcessToJobObject(job', start),
                        text.index('api.ResumeThread(info_process.thread)', start))
        self.assertNotIn('--no-sandbox', text)
        flags = integer_flags(call_named('Windows标准用户验收v22.py', 'CreateProcessWithLogonW').args[6])
        self.assertEqual(flags & (0x02000000 | 0x01000000 | 0x08000000), 0)


if __name__ == '__main__':
    unittest.main()
