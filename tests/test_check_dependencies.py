import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "hooks"))

import check_dependencies as cd  # noqa: E402


class TestCommandExtraction(unittest.TestCase):
    def test_npm_install_with_version(self):
        pkgs = cd.extract_packages_from_command("npm install moment@2.29.4 --save")
        self.assertEqual(pkgs, ["moment"])

    def test_python_m_pip_and_prefixes(self):
        cmd = "FOO=bar sudo -E python3 -m pip install requests>=2.28"
        pkgs = cd.extract_packages_from_command(cmd)
        self.assertEqual(pkgs, ["requests"])

    def test_chained_commands(self):
        cmd = "npm install lodash && pip install requests"
        pkgs = cd.extract_packages_from_command(cmd)
        self.assertEqual(pkgs, ["lodash", "requests"])

    def test_pip_requirement_flag_skips_next_token(self):
        cmd = "pip install -r requirements.txt requests"
        pkgs = cd.extract_packages_from_command(cmd)
        self.assertEqual(pkgs, ["requests"])


class TestImportExtraction(unittest.TestCase):
    def test_python_ignores_commented_imports(self):
        content = "# import requests\nimport httpx\n"
        pkgs = cd.extract_packages_from_content(content, "app.py")
        self.assertEqual(pkgs, ["httpx"])

    def test_js_ignores_line_and_block_comments(self):
        content = "// import moment from 'moment'\n/* require('lodash') */\nimport x from 'date-fns'\n"
        pkgs = cd.extract_packages_from_content(content, "app.ts")
        self.assertEqual(pkgs, ["date-fns"])

    def test_go_ignores_commented_imports(self):
        content = "// import \"github.com/user/moment\"\nimport \"github.com/team/httpx\"\n"
        pkgs = cd.extract_packages_from_content(content, "main.go")
        self.assertEqual(pkgs, ["httpx", "github.com/team/httpx"])


class TestNormalization(unittest.TestCase):
    def test_pip_name_normalization(self):
        self.assertEqual(cd._normalise_pip("My_Pkg.Name>=1.2"), "my-pkg-name")


if __name__ == "__main__":
    unittest.main()
