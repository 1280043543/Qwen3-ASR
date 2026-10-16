import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


@unittest.skipUnless(sys.platform == 'win32', 'Windows shortcut properties')
class WindowsShellTests(unittest.TestCase):
    def test_shortcut_has_same_app_id_as_running_process(self):
        self.assertIsNotNone(importlib.util.find_spec('qwen_local_subtitles.windows_shell'),
                             'Shortcut and process need a shared Windows identity')
        from qwen_local_subtitles.windows_shell import APP_ID, set_shortcut_app_id
        with tempfile.TemporaryDirectory() as folder:
            link = Path(folder) / 'subtitle.lnk'
            env = dict(os.environ, QWEN_TEST_LINK=str(link))
            create = "$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:QWEN_TEST_LINK); $s.TargetPath=$env:SystemRoot+'\\System32\\notepad.exe'; $s.Save()"
            subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', create],
                           env=env, check=True, capture_output=True)
            set_shortcut_app_id(link)
            read = "$p=Get-Item -LiteralPath $env:QWEN_TEST_LINK; $s=New-Object -ComObject Shell.Application; $s.NameSpace($p.DirectoryName).ParseName($p.Name).ExtendedProperty('System.AppUserModel.ID')"
            result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', read],
                                    env=env, check=True, capture_output=True, text=True)
            self.assertEqual(result.stdout.strip(), APP_ID)


if __name__ == '__main__':
    unittest.main()

