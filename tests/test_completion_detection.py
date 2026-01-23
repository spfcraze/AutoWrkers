import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.session_manager import COMPLETION_PATTERNS


class TestCompletionPatterns:
    def test_complete_with_newline(self):
        content = "Some output\n/complete\nMore output"
        assert any(pattern in content for pattern in COMPLETION_PATTERNS)

    def test_complete_with_space(self):
        content = "Some output /complete followed by text"
        assert any(pattern in content for pattern in COMPLETION_PATTERNS)

    def test_complete_with_carriage_return(self):
        content = "Some output\r/complete\rMore output"
        assert any(pattern in content for pattern in COMPLETION_PATTERNS)

    def test_done_with_newline(self):
        content = "Task finished\n/done\n"
        assert any(pattern in content for pattern in COMPLETION_PATTERNS)

    def test_done_with_space(self):
        content = "Task finished /done "
        assert any(pattern in content for pattern in COMPLETION_PATTERNS)

    def test_no_match_partial(self):
        content = "This is /completing but not complete"
        matches = [pattern for pattern in COMPLETION_PATTERNS if pattern in content]
        assert len(matches) == 0

    def test_no_match_in_word(self):
        content = "incomplete work"
        assert not any(pattern in content for pattern in COMPLETION_PATTERNS)

    def test_case_sensitive(self):
        content = "/COMPLETE\n"
        assert not any(pattern in content for pattern in COMPLETION_PATTERNS)

    def test_detection_in_recent_content(self):
        recent_content = "Claude: I've finished the task. /complete\n"
        assert any(pattern in recent_content for pattern in COMPLETION_PATTERNS)

    def test_multiple_patterns_in_content(self):
        content = "/done\n some text /complete\n"
        matches = [pattern for pattern in COMPLETION_PATTERNS if pattern in content]
        assert len(matches) >= 2


class TestCompletionPatternsEdgeCases:
    def test_empty_content(self):
        content = ""
        assert not any(pattern in content for pattern in COMPLETION_PATTERNS)

    def test_only_slash(self):
        content = "/"
        assert not any(pattern in content for pattern in COMPLETION_PATTERNS)

    def test_complete_at_start(self):
        content = "/complete\nrest of output"
        assert any(pattern in content for pattern in COMPLETION_PATTERNS)

    def test_complete_at_end(self):
        content = "output before /complete\n"
        assert any(pattern in content for pattern in COMPLETION_PATTERNS)

    def test_long_content_with_pattern(self):
        content = "x" * 10000 + "\n/complete\n" + "y" * 10000
        assert any(pattern in content for pattern in COMPLETION_PATTERNS)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
