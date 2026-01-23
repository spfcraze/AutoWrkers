import pytest
import asyncio
import tempfile
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.automation import VerificationRunner
from src.models import VerificationResult


class TestVerificationRunnerCommand:
    @pytest.mark.asyncio
    async def test_successful_command(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = await VerificationRunner.run_command("echo 'hello'", tmpdir)
            assert result.passed is True
            assert "hello" in result.output
            assert result.duration_ms >= 0

    @pytest.mark.asyncio
    async def test_failing_command(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = await VerificationRunner.run_command("exit 1", tmpdir)
            assert result.passed is False

    @pytest.mark.asyncio
    async def test_command_with_output(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = await VerificationRunner.run_command("echo 'line1' && echo 'line2'", tmpdir)
            assert result.passed is True
            assert "line1" in result.output
            assert "line2" in result.output

    @pytest.mark.asyncio
    async def test_command_timeout(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = await VerificationRunner.run_command("sleep 10", tmpdir, timeout=1)
            assert result.passed is False
            assert "timed out" in result.output.lower()

    @pytest.mark.asyncio
    async def test_command_stderr(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = await VerificationRunner.run_command("echo 'error' >&2", tmpdir)
            assert "error" in result.output

    @pytest.mark.asyncio
    async def test_command_in_working_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("content")
            result = await VerificationRunner.run_command("cat test.txt", tmpdir)
            assert result.passed is True
            assert "content" in result.output

    @pytest.mark.asyncio
    async def test_invalid_command(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = await VerificationRunner.run_command("nonexistent_command_xyz", tmpdir)
            assert result.passed is False


class TestVerificationResult:
    def test_verification_result_defaults(self):
        result = VerificationResult(
            check_type="test",
            passed=True,
            output="All tests passed"
        )
        assert result.check_type == "test"
        assert result.passed is True
        assert result.output == "All tests passed"
        assert result.duration_ms == 0

    def test_verification_result_with_duration(self):
        result = VerificationResult(
            check_type="lint",
            passed=False,
            output="3 errors found",
            duration_ms=1500
        )
        assert result.duration_ms == 1500

    def test_verification_result_to_dict(self):
        result = VerificationResult(
            check_type="build",
            passed=True,
            output="Build successful",
            duration_ms=5000
        )
        d = result.to_dict()
        assert d["check_type"] == "build"
        assert d["passed"] is True
        assert d["output"] == "Build successful"
        assert d["duration_ms"] == 5000


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
