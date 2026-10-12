# tests/unit/test_batch.py
#
# Unit tests for batch processing utilities (isir.utils.batch).
# Covers recursive .isir discovery and the run_batch helper, including
# success, failure, kwargs forwarding, ordering, and timeout handling.

import time
import pytest
from pathlib import Path
from isir.utils.batch import find_isir_files, run_batch


class TestFindIsirFiles:
    def test_recursive_discovery(self, tmp_path):
        (tmp_path / "sub" / "deep").mkdir(parents=True)
        (tmp_path / "a.isir").write_text("")
        (tmp_path / "b.isir").write_text("")
        (tmp_path / "sub" / "c.isir").write_text("")
        (tmp_path / "sub" / "deep" / "d.isir").write_text("")
        (tmp_path / "notes.txt").write_text("")
        (tmp_path / "sub" / "x.v").write_text("")

        found = find_isir_files(tmp_path)

        expected = [
            tmp_path / "a.isir",
            tmp_path / "b.isir",
            tmp_path / "sub" / "c.isir",
            tmp_path / "sub" / "deep" / "d.isir",
        ]
        assert found == sorted(expected)
        assert all(p.is_absolute() for p in found)

    def test_non_recursive_only_top_level(self, tmp_path):
        (tmp_path / "sub").mkdir()
        (tmp_path / "top.isir").write_text("")
        (tmp_path / "sub" / "nested.isir").write_text("")

        found = find_isir_files(tmp_path, recursive=False)

        assert found == [tmp_path / "top.isir"]

    def test_empty_directory(self, tmp_path):
        assert find_isir_files(tmp_path) == []

    def test_directory_with_no_matching_files(self, tmp_path):
        (tmp_path / "a.txt").write_text("")
        (tmp_path / "b.v").write_text("")
        assert find_isir_files(tmp_path) == []

    def test_nonexistent_directory_raises(self, tmp_path):
        missing = tmp_path / "does_not_exist"
        with pytest.raises(NotADirectoryError):
            find_isir_files(missing)

    def test_file_instead_of_directory_raises(self, tmp_path):
        some_file = tmp_path / "not_a_dir.isir"
        some_file.write_text("")
        with pytest.raises(NotADirectoryError):
            find_isir_files(some_file)

    def test_custom_pattern(self, tmp_path):
        (tmp_path / "sub").mkdir()
        (tmp_path / "a.v").write_text("")
        (tmp_path / "b.v").write_text("")
        (tmp_path / "c.isir").write_text("")
        (tmp_path / "sub" / "d.v").write_text("")

        found = find_isir_files(tmp_path, pattern="*.v")

        assert found == sorted([
            tmp_path / "a.v",
            tmp_path / "b.v",
            tmp_path / "sub" / "d.v",
        ])

    def test_accepts_string_directory(self, tmp_path):
        (tmp_path / "a.isir").write_text("")
        found = find_isir_files(str(tmp_path))
        assert found == [tmp_path / "a.isir"]


class TestRunBatch:
    def test_success_collects_results(self, tmp_path):
        files = [tmp_path / "a.isir", tmp_path / "b.isir"]
        for f in files:
            f.write_text("")

        def worker(path):
            return f"processed:{path.name}"

        results = run_batch(worker, files, show_progress=False)

        assert len(results) == 2
        assert [r["file"] for r in results] == [str(f) for f in files]
        assert all(r["success"] for r in results)
        assert results[0]["result"] == "processed:a.isir"
        assert results[1]["result"] == "processed:b.isir"
        assert all(r["error"] is None for r in results)
        assert all(isinstance(r["duration"], float) for r in results)

    def test_failure_captures_error_message(self, tmp_path):
        files = [tmp_path / "boom.isir"]
        files[0].write_text("")

        def worker(path):
            raise ValueError("something broke")

        results = run_batch(worker, files, show_progress=False)

        assert len(results) == 1
        assert results[0]["success"] is False
        assert results[0]["result"] is None
        assert results[0]["error"] == "something broke"

    def test_forwards_kwargs_to_worker(self, tmp_path):
        files = [tmp_path / "a.isir"]
        files[0].write_text("")
        captured = {}

        def worker(path, *, flag, value):
            captured["flag"] = flag
            captured["value"] = value
            return "ok"

        results = run_batch(worker, files, show_progress=False, flag=True, value=42)

        assert results[0]["success"] is True
        assert captured == {"flag": True, "value": 42}

    def test_mixed_success_and_failure_preserves_order(self, tmp_path):
        files = [tmp_path / "ok.isir", tmp_path / "fail.isir", tmp_path / "ok2.isir"]
        for f in files:
            f.write_text("")

        def worker(path):
            if "fail" in path.name:
                raise RuntimeError("nope")
            return path.name

        results = run_batch(worker, files, show_progress=False)

        assert [r["file"] for r in results] == [str(f) for f in files]
        assert [r["success"] for r in results] == [True, False, True]
        assert results[1]["error"] == "nope"

    def test_empty_file_list(self):
        assert run_batch(lambda p: None, [], show_progress=False) == []

    def test_timeout_path(self, tmp_path):
        files = [tmp_path / "slow.isir"]
        files[0].write_text("")

        def worker(path):
            time.sleep(0.15)
            return "done"

        results = run_batch(worker, files, timeout_per_file=0.01, show_progress=False)

        assert len(results) == 1
        assert results[0]["success"] is False
        assert results[0]["result"] is None
        assert "timed out after" in results[0]["error"]

    def test_timeout_does_not_affect_other_files(self, tmp_path):
        files = [tmp_path / "slow.isir", tmp_path / "fast.isir"]
        for f in files:
            f.write_text("")

        def worker(path):
            if path.name == "slow.isir":
                time.sleep(0.15)
            return path.name

        results = run_batch(worker, files, timeout_per_file=0.01, show_progress=False)

        assert results[0]["success"] is False
        assert results[1]["success"] is True
        assert results[1]["result"] == "fast.isir"
