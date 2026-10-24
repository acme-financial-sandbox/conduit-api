# coding: utf-8
"""Oracle characterization tests for the Click commands in ``conduit/commands.py`` and app wiring."""
import pytest

from conduit import commands

from .oracle_helpers import assert_matches_golden_text


@pytest.fixture
def runner(app):
    return app.test_cli_runner()


def test_registered_commands(app):
    assert set(app.cli.commands) == {'clean', 'db', 'lint', 'test', 'urls'}


def test_shell_context(app):
    assert set(app.make_shell_context()) == {'Article', 'Comment', 'Tag', 'User', 'UserProfile',
                                             'app', 'db', 'g'}


class TestUrls:

    def test_full_listing(self, runner):
        result = runner.invoke(commands.urls, [])
        assert result.exit_code == 0
        assert_matches_golden_text('cli_urls.txt', result.output)

    def test_order_by_endpoint(self, runner):
        result = runner.invoke(commands.urls, ['--order', 'endpoint'])
        assert result.exit_code == 0
        rows = [line.split()[1] for line in result.output.splitlines()[2:]]
        assert rows[0] == 'articles.articles_feed'
        assert rows == sorted(rows)

    def test_unknown_url(self, runner):
        result = runner.invoke(commands.urls, ['--url', '/nope'])
        assert result.exit_code == 0
        assert result.output.splitlines()[2].startswith('<404 Not Found: ')

    # ORACLE: encodes current (buggy) behavior — revisit after upgrade
    @pytest.mark.oracle_known_bug
    def test_matching_url_crashes(self, runner):
        """Formatting the ``arguments`` dict with a width spec raises."""
        result = runner.invoke(commands.urls, ['--url', '/api/articles/foo'])
        assert result.exit_code == 1
        assert isinstance(result.exception, TypeError)
        assert 'Arguments' in result.output.splitlines()[0]

    def test_unknown_order(self, runner):
        result = runner.invoke(commands.urls, ['--order', 'bogus'])
        assert result.exit_code == 1
        assert isinstance(result.exception, AttributeError)


class TestClean:

    def test_removes_pyc_and_pyo_only(self, runner, tmp_path, monkeypatch):
        (tmp_path / 'sub').mkdir()
        for name in ('a.pyc', 'sub/b.pyo', 'c.py', 'd.txt'):
            (tmp_path / name).write_text('x')
        monkeypatch.chdir(str(tmp_path))
        result = runner.invoke(commands.clean, [])
        assert result.exit_code == 0
        assert sorted(result.output.splitlines()) == ['Removing ./a.pyc', 'Removing ./sub/b.pyo']
        remaining = sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob('*') if p.is_file())
        assert remaining == ['c.py', 'd.txt']


class TestLint:

    @pytest.fixture
    def project(self, tmp_path, monkeypatch):
        for name in ('pkg', 'requirements', '.hidden'):
            (tmp_path / name).mkdir()
        (tmp_path / 'x.py').write_text('')
        monkeypatch.chdir(str(tmp_path))

    @pytest.fixture
    def calls(self, monkeypatch):
        class Calls(list):
            rc = 0

        recorded = Calls()

        def fake_call(command_line):
            recorded.append(command_line)
            return recorded.rc

        monkeypatch.setattr(commands, 'call', fake_call)
        return recorded

    def test_runs_flake8_on_root_files_and_dirs(self, runner, project, calls):
        result = runner.invoke(commands.lint, [])
        assert result.exit_code == 0
        assert calls == [['flake8', 'x.py', 'pkg']]
        assert result.output == 'Checking code style: flake8 x.py pkg\n'

    def test_failure_exit_code(self, runner, project, calls):
        calls.rc = 3
        assert runner.invoke(commands.lint, []).exit_code == 3

    def test_fix_imports_runs_isort_first(self, runner, project, calls):
        result = runner.invoke(commands.lint, ['--fix-imports'])
        assert result.exit_code == 0
        assert calls == [['isort', '-rc', 'x.py', 'pkg'], ['flake8', 'x.py', 'pkg']]


class TestTestCommand:

    def test_runs_pytest_on_tests_dir(self, runner, monkeypatch):
        seen = []
        monkeypatch.setattr(pytest, 'main', lambda args: seen.append(args) or 5)
        result = runner.invoke(commands.test, [])
        assert result.exit_code == 5
        assert seen == [[commands.TEST_PATH, '--verbose']]
