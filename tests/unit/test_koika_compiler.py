# tests/unit/test_koika_compiler.py
#
# Unit tests for the Kōika compiler backend (koika_compiler.py).
# Tests compiler path resolution and compile_ocaml_to_verilog functionality.

import json as real_json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from specir.backends.koika_compiler import (
    _find_compiler,
    compile_ocaml_to_verilog,
    KoikaCompilationError
)
from specir.dialects.rtl_ir import RTLModuleContainer


class TestFindCompiler(unittest.TestCase):
    """Tests for _find_compiler path resolution."""

    @patch("pathlib.Path.exists", return_value=True)
    def test_explicit_path_exists(self, mock_exists):
        """If an explicit path is given and exists, return it."""
        result = _find_compiler(koika_path="/custom/path/koika")
        self.assertEqual(result, Path("/custom/path/koika"))

    @patch("pathlib.Path.exists", return_value=False)
    def test_explicit_path_not_exists_raises(self, mock_exists):
        """If an explicit path is given but doesn't exist, raise error."""
        with self.assertRaises(KoikaCompilationError) as ctx:
            _find_compiler(koika_path="/nonexistent/koika")
        self.assertIn("not found at", str(ctx.exception))

    @patch("shutil.which", return_value="/usr/local/bin/koika")
    @patch("pathlib.Path.exists", return_value=False)
    def test_found_on_path(self, mock_exists, mock_which):
        """If koika is found on PATH, return that path."""
        result = _find_compiler(koika_path=None)
        self.assertEqual(result, Path("/usr/local/bin/koika"))

    @patch("shutil.which", return_value=None)
    @patch.object(Path, "exists", side_effect=[False, True])
    def test_found_in_common_location(self, mock_exists, mock_which):
        """If not on PATH, check common locations."""
        result = _find_compiler(koika_path=None)
        self.assertEqual(result, Path("/usr/local/bin/koika"))

    @patch("shutil.which", return_value=None)
    @patch.object(Path, "exists", return_value=False)
    def test_not_found_anywhere_raises(self, mock_exists, mock_which):
        """If not found on PATH or in common locations, raise error."""
        with self.assertRaises(KoikaCompilationError) as ctx:
            _find_compiler(koika_path=None)
        self.assertIn("Kōika compiler not found", str(ctx.exception))


class TestCompileOCamlToVerilog(unittest.TestCase):
    """Tests for compile_ocaml_to_verilog with mocked subprocess and compiler lookup."""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.output_dir = Path(self.tmp_dir.name)
        self.design_name = "test_design"
        self.compiler_path = Path("/usr/bin/koika")

        self.ml_path = self.output_dir / f"{self.design_name}.ml"
        self.ml_path.write_text("(* dummy *)")

        self.verilog_path = self.output_dir / f"{self.design_name}.v"
        self.verilog_path.write_text("module test_design(); endmodule")

        self.mapping_path = self.output_dir / "mapping.json"
        self.mapping_path.write_text(real_json.dumps({"mapping": []}))

    def tearDown(self):
        self.tmp_dir.cleanup()

    @patch("specir.backends.koika_compiler._find_compiler")
    @patch("subprocess.run")
    def test_successful_compilation(self, mock_run, mock_find):
        mock_find.return_value = self.compiler_path
        mock_run.return_value.returncode = 0

        container = compile_ocaml_to_verilog(self.design_name, self.output_dir)

        self.assertIsInstance(container, RTLModuleContainer)
        self.assertEqual(container.design_name, self.design_name)

    @patch("specir.backends.koika_compiler._find_compiler")
    @patch("subprocess.run")
    def test_compiler_error_raises(self, mock_run, mock_find):
        mock_find.return_value = self.compiler_path
        mock_run.return_value.returncode = 1
        mock_run.return_value.stderr = "error message"

        with self.assertRaises(KoikaCompilationError) as ctx:
            compile_ocaml_to_verilog(self.design_name, self.output_dir)
        self.assertIn("Kōika compilation failed", str(ctx.exception))

    @patch("specir.backends.koika_compiler._find_compiler")
    @patch("subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 300, output=b"", stderr=b""))
    def test_timeout_raises(self, mock_run, mock_find):
        mock_find.return_value = self.compiler_path

        with self.assertRaises(KoikaCompilationError) as ctx:
            compile_ocaml_to_verilog(self.design_name, self.output_dir)
        self.assertIn("timed out", str(ctx.exception))

    @patch("specir.backends.koika_compiler._find_compiler")
    @patch("subprocess.run")
    def test_compiler_command_args(self, mock_run, mock_find):
        mock_find.return_value = self.compiler_path
        mock_run.return_value.returncode = 0

        compile_ocaml_to_verilog(self.design_name, self.output_dir)

        expected_cmd = [
            str(self.compiler_path),
            str(self.ml_path),
            "-T", "verilog",
            "-o", str(self.output_dir)
        ]
        mock_run.assert_called_once()
        actual_cmd = mock_run.call_args[0][0]
        self.assertEqual(actual_cmd, expected_cmd)


if __name__ == "__main__":
    unittest.main()
