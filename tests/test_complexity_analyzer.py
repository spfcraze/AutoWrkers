import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.automation import IssueComplexityAnalyzer, ContextBuilder
from src.models import IssueSession, IssueSessionStatus


def make_issue_session(
    body: str = "",
    labels: list = None,
    title: str = "Test Issue"
) -> IssueSession:
    return IssueSession(
        id=1,
        project_id=1,
        github_issue_number=1,
        github_issue_title=title,
        github_issue_body=body,
        github_issue_labels=labels or [],
        github_issue_url="https://github.com/test/repo/issues/1",
        status=IssueSessionStatus.PENDING
    )


class TestContextBuilderExtractFileReferences:
    def test_extracts_backtick_files(self):
        text = "Please fix the bug in `src/server.py` and `tests/test_main.py`"
        files = ContextBuilder.extract_file_references(text)
        assert "src/server.py" in files
        assert "tests/test_main.py" in files

    def test_extracts_inline_files(self):
        text = "The error is in main.py around line 42"
        files = ContextBuilder.extract_file_references(text)
        assert "main.py" in files

    def test_extracts_files_with_in_prefix(self):
        text = "Found the bug in utils/helpers.ts"
        files = ContextBuilder.extract_file_references(text)
        assert "utils/helpers.ts" in files

    def test_ignores_non_file_patterns(self):
        text = "Use version 1.2.3 of the library"
        files = ContextBuilder.extract_file_references(text)
        assert "1.2.3" not in files

    def test_empty_text(self):
        files = ContextBuilder.extract_file_references("")
        assert files == []


class TestIssueComplexityAnalyzer:
    def test_simple_issue_low_score(self):
        session = make_issue_session(body="Fix typo in README")
        score, explanation = IssueComplexityAnalyzer.analyze(session)
        assert score == 0
        assert explanation == "standard issue"

    def test_many_files_increases_score(self):
        body = """
        Fix bugs in:
        - `src/server.py`
        - `src/client.py`
        - `src/models.py`
        - `src/utils.py`
        - `tests/test_all.py`
        """
        session = make_issue_session(body=body)
        score, explanation = IssueComplexityAnalyzer.analyze(session)
        assert score > 0
        assert "files mentioned" in explanation

    def test_long_body_increases_score(self):
        body = "x" * 3000
        session = make_issue_session(body=body)
        score, explanation = IssueComplexityAnalyzer.analyze(session)
        assert score > 0
        assert "long description" in explanation

    def test_many_code_blocks_increases_score(self):
        body = """
        ```python
        def foo():
            pass
        ```
        ```python
        def bar():
            pass
        ```
        ```python
        def baz():
            pass
        ```
        """
        session = make_issue_session(body=body)
        score, explanation = IssueComplexityAnalyzer.analyze(session)
        assert score > 0
        assert "code blocks" in explanation

    def test_complex_labels_increase_score(self):
        session = make_issue_session(body="Simple bug", labels=["security", "breaking-change"])
        score, explanation = IssueComplexityAnalyzer.analyze(session)
        assert score >= 10
        assert "security" in explanation or "breaking-change" in explanation

    def test_is_too_complex_threshold(self):
        simple = make_issue_session(body="Fix typo")
        is_complex, score, _ = IssueComplexityAnalyzer.is_too_complex(simple, threshold=20)
        assert not is_complex

        complex_body = "x" * 5000 + "\n".join([f"`file{i}.py`" for i in range(10)])
        complex_session = make_issue_session(body=complex_body, labels=["architecture"])
        is_complex, score, _ = IssueComplexityAnalyzer.is_too_complex(complex_session, threshold=20)
        assert is_complex
        assert score >= 20

    def test_none_body_handled(self):
        session = make_issue_session()
        session.github_issue_body = None
        score, explanation = IssueComplexityAnalyzer.analyze(session)
        assert score == 0


class TestContextBuilderExtractErrorReferences:
    def test_extracts_error_types(self):
        text = "Getting a TypeError and ValueError"
        refs = ContextBuilder.extract_error_references(text)
        assert "TypeError" in refs
        assert "ValueError" in refs

    def test_extracts_function_names(self):
        text = "The issue is in function processData"
        refs = ContextBuilder.extract_error_references(text)
        assert "processData" in refs

    def test_extracts_class_names(self):
        text = "Bug in class UserManager"
        refs = ContextBuilder.extract_error_references(text)
        assert "UserManager" in refs


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
