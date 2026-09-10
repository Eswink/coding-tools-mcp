"""Startup diagnostics contracts, not actual Windows acceptance."""
import importlib.util
from pathlib import Path
from unittest.mock import Mock, patch
import tempfile
import unittest
spec = importlib.util.spec_from_file_location("stdio_host", Path(__file__).with_name("Windows原生宿主v13.py"))
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

class HostTests(unittest.TestCase):
    def test_rejects_non_hosted_user_machine(self):
        with patch.dict(m.os.environ, {}, clear=True), self.assertRaises(RuntimeError):
            m.run(Path("app"), Path("log"), Path("result"))
    def test_exact_binary_stdio_and_exit_code_are_retained(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); app=root/"app.exe"; app.write_bytes(b"fixture")
            env={"GITHUB_ACTIONS":"true", "RUNNER_ENVIRONMENT":"github-hosted", "GITHUB_REPOSITORY":"Eswink/coding-tools-mcp"}
            child=Mock(pid=42); child.wait.return_value=0xc0000142
            with patch.dict(m.os.environ, env, clear=True), patch.object(m.sys,"platform","win32"), patch.object(m.subprocess,"Popen",return_value=child) as launch:
                self.assertEqual(m.run(app,root/"out.log",root/"out.json"),0xc0000142)
                self.assertEqual(launch.call_args.args,([str(app.resolve())],))
                self.assertTrue(launch.call_args.kwargs["close_fds"])
                self.assertEqual(launch.call_args.kwargs["stderr"],m.subprocess.STDOUT)
                self.assertEqual(m.json.loads((root/"out.json").read_text())["exit_code_hex"],"0xc0000142")

if __name__ == "__main__": unittest.main()
