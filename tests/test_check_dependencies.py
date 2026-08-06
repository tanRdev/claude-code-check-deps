import io
import json
import sys
import unittest
from pathlib import Path
from unittest import mock


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


class TestComposerSupport(unittest.TestCase):
    def test_composer_require_vendor_package(self):
        pkgs = cd.extract_packages_from_command("composer require moment/moment")
        self.assertIn("moment", pkgs)
        self.assertIn("moment/moment", pkgs)

    def test_composer_require_with_version_constraint(self):
        pkgs = cd.extract_packages_from_command("composer require phpoffice/phpspreadsheet:^1.0")
        self.assertIn("phpoffice/phpspreadsheet", pkgs)

    def test_composer_global_require(self):
        pkgs = cd.extract_packages_from_command("composer global require laravel/installer")
        self.assertIn("laravel/installer", pkgs)


class TestExecRunners(unittest.TestCase):
    def test_npx_executes_package(self):
        self.assertIn("moment", cd.extract_packages_from_command("npx moment"))

    def test_npx_with_flags_and_version(self):
        self.assertIn("moment", cd.extract_packages_from_command("npx -y moment@2.29.4"))

    def test_npm_exec(self):
        self.assertIn("lodash", cd.extract_packages_from_command("npm exec -- lodash"))

    def test_pipx_run(self):
        self.assertIn("requests", cd.extract_packages_from_command("pipx run requests"))

    def test_uvx(self):
        self.assertIn("requests", cd.extract_packages_from_command("uvx requests"))

    def test_uv_tool_run(self):
        self.assertIn("requests", cd.extract_packages_from_command("uv tool run requests"))

    def test_bunx(self):
        self.assertIn("lodash", cd.extract_packages_from_command("bunx lodash"))

    def test_bun_x(self):
        self.assertIn("lodash", cd.extract_packages_from_command("bun x lodash"))

    def test_pnpm_dlx(self):
        self.assertIn("lodash", cd.extract_packages_from_command("pnpm dlx lodash"))

    def test_yarn_dlx(self):
        self.assertIn("lodash", cd.extract_packages_from_command("yarn dlx lodash"))


class TestUrlInstalls(unittest.TestCase):
    def test_pip_git_url(self):
        pkgs = cd.extract_packages_from_command(
            "pip install git+https://github.com/psf/requests.git")
        self.assertIn("requests", pkgs)

    def test_pip_git_url_with_egg_fragment(self):
        pkgs = cd.extract_packages_from_command(
            "pip install git+https://github.com/psf/requests#egg=requests")
        self.assertIn("requests", pkgs)

    def test_pip_https_archive(self):
        pkgs = cd.extract_packages_from_command(
            "pip install https://files.pythonhosted.org/packages/requests-2.31.0.tar.gz")
        self.assertIn("requests", pkgs)

    def test_pip_pep508_direct_reference(self):
        pkgs = cd.extract_packages_from_command(
            "pip install 'requests @ git+https://github.com/psf/requests.git'")
        self.assertIn("requests", pkgs)

    def test_npm_github_shorthand(self):
        pkgs = cd.extract_packages_from_command("npm install github:user/moment")
        self.assertIn("moment", pkgs)

    def test_npm_user_repo_shorthand(self):
        pkgs = cd.extract_packages_from_command("npm install user/moment")
        self.assertIn("moment", pkgs)

    def test_unresolvable_url_flagged_conservatively(self):
        _, reasons = cd.analyze_command("pip install https://example.com")
        self.assertTrue(reasons)

    def test_local_paths_not_flagged(self):
        _, reasons = cd.analyze_command("pip install ./local-dir")
        self.assertEqual(reasons, [])

    def test_pip_editable_vcs_url(self):
        pkgs = cd.extract_packages_from_command(
            "pip install -e git+https://github.com/psf/requests.git#egg=requests")
        self.assertIn("requests", pkgs)

    def test_pip_editable_equals_form(self):
        pkgs = cd.extract_packages_from_command(
            "pip install --editable=git+https://github.com/psf/requests.git")
        self.assertIn("requests", pkgs)

    def test_pip_editable_local_path_allowed(self):
        pkgs, reasons = cd.analyze_command("pip install -e .")
        self.assertEqual(pkgs, [])
        self.assertEqual(reasons, [])

    def test_uv_pip_install_editable_url(self):
        pkgs = cd.extract_packages_from_command(
            "uv pip install -e git+https://github.com/psf/requests.git")
        self.assertIn("requests", pkgs)


class TestFailClosed(unittest.TestCase):
    def test_malformed_pm_command_flagged(self):
        _, reasons = cd.analyze_command('npm install "unterminated')
        self.assertTrue(reasons)

    def test_malformed_pip_command_flagged(self):
        _, reasons = cd.analyze_command('pip install "unterminated')
        self.assertTrue(reasons)

    def test_malformed_non_pm_command_allowed(self):
        _, reasons = cd.analyze_command('echo "unterminated')
        self.assertEqual(reasons, [])


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

    def test_js_ignores_trailing_line_comment(self):
        content = "const x = 1; // import moment from 'moment'\nimport y from 'date-fns'\n"
        pkgs = cd.extract_packages_from_content(content, "app.ts")
        self.assertEqual(pkgs, ["date-fns"])

    def test_js_keeps_url_strings_intact(self):
        content = "const u = 'https://example.com/a.js'\n"
        pkgs = cd.extract_packages_from_content(content, "app.js")
        self.assertEqual(pkgs, [])

    def test_go_ignores_trailing_line_comment(self):
        content = "package main // import \"github.com/user/moment\"\n"
        pkgs = cd.extract_packages_from_content(content, "main.go")
        self.assertEqual(pkgs, [])

    def test_python_ignores_docstring_imports(self):
        content = '"""Module.\n\nimport requests\n"""\nimport httpx\n'
        pkgs = cd.extract_packages_from_content(content, "app.py")
        self.assertEqual(pkgs, ["httpx"])

    def test_go_relative_import_allowed(self):
        content = 'import "./moment"\nimport "../pkg/lodash"\n'
        pkgs = cd.extract_packages_from_content(content, "main.go")
        self.assertEqual(pkgs, [])

    def test_go_get_relative_allowed(self):
        pkgs = cd.extract_packages_from_command("go get ./...")
        self.assertEqual(pkgs, [])


class TestNormalization(unittest.TestCase):
    def test_pip_name_normalization(self):
        self.assertEqual(cd._normalise_pip("My_Pkg.Name>=1.2"), "my-pkg-name")


class TestMain(unittest.TestCase):
    def run_main(self, payload, rules=None):
        if not isinstance(payload, str):
            payload = json.dumps(payload)
        patches = [mock.patch("sys.stdin", io.StringIO(payload))]
        if rules is not None:
            patches.append(mock.patch.object(cd, "load_rules", return_value=rules))
        for p in patches:
            p.start()
        try:
            with self.assertRaises(SystemExit) as ctx:
                cd.main()
        finally:
            for p in patches:
                p.stop()
        return ctx.exception.code

    def test_clean_command_allowed(self):
        code = self.run_main(
            {"tool_name": "Bash", "tool_input": {"command": "npm install date-fns"}})
        self.assertEqual(code, 0)

    def test_blocked_dependency_blocked(self):
        code = self.run_main(
            {"tool_name": "Bash", "tool_input": {"command": "npm install moment"}})
        self.assertEqual(code, 2)

    def test_blocked_write_import_blocked(self):
        code = self.run_main(
            {"tool_name": "Write",
             "tool_input": {"file_path": "app.py", "content": "import requests"}})
        self.assertEqual(code, 2)

    def test_fail_closed_on_unparseable_pm_command(self):
        code = self.run_main(
            {"tool_name": "Bash", "tool_input": {"command": 'npm install "unterminated'}})
        self.assertEqual(code, 2)

    def test_fail_closed_on_opaque_url_install(self):
        code = self.run_main(
            {"tool_name": "Bash", "tool_input": {"command": "pip install https://example.com"}})
        self.assertEqual(code, 2)

    def test_hook_disabled_allows_everything(self):
        code = self.run_main(
            {"tool_name": "Bash", "tool_input": {"command": "npm install moment"}},
            rules={})
        self.assertEqual(code, 0)

    def test_malformed_input_exits_nonzero(self):
        code = self.run_main("not json")
        self.assertEqual(code, 1)

    def test_unrelated_tool_allowed(self):
        code = self.run_main({"tool_name": "Read", "tool_input": {}})
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
