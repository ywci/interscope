# tests/unit/test_verilator_sim.py
#
# Unit tests for the Verilator simulation backend.
# Verifies testbench generation and error handling without external tools.

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from specir.backends import verilator_sim
from specir.backends.verilator_sim import (
    VerilatorError,
    generate_testbench,
    build_simulation,
    run_simulation,
    simulate
)


@pytest.fixture
def tmp_dir(tmp_path):
    return tmp_path


class TestGenerateTestbench:
    def test_generates_valid_cpp(self, tmp_dir):
        """The generated testbench includes the top module, VCD tracing, and cycle loop."""
        tb_path = tmp_dir / "sim_main.cpp"
        result = generate_testbench(
            top_module="my_fifo",
            output_path=tb_path,
            vcd_filename="trace.vcd",
            cycles=10,
            rst_active=0,
            rst_inactive=1
        )
        assert result == tb_path
        content = tb_path.read_text()
        assert '#include "Vmy_fifo.h"' in content
        assert 'VerilatedVcdC' in content
        assert 'trace.vcd' in content
        assert 'for (int cycle = 0; cycle < 10; cycle++)' in content
        assert 'top->rst_n = 0;' in content
        assert 'top->rst_n = 1;' in content

    def test_defaults(self, tmp_dir):
        """Test the default values for reset polarity and cycles."""
        tb_path = tmp_dir / "sim_main.cpp"
        generate_testbench(
            top_module="top",
            output_path=tb_path
        )
        content = tb_path.read_text()
        # Default cycles = 1000
        assert 'for (int cycle = 0; cycle < 1000; cycle++)' in content


class TestBuildSimulation:
    def test_missing_verilator(self, tmp_dir):
        """If verilator is not found, VerilatorError is raised."""
        with patch("shutil.which", return_value=None):
            with pytest.raises(VerilatorError, match="Verilator not found"):
                build_simulation(
                    rtl_paths=[tmp_dir / "dummy.v"],
                    top_module="top",
                    output_dir=tmp_dir
                )

    def test_verilator_found_but_build_fails(self, tmp_dir):
        """If verilator is found but the build command fails, an error is raised."""
        dummy_v = tmp_dir / "dummy.v"
        dummy_v.write_text("module top; endmodule")
        with patch("shutil.which", return_value="/usr/bin/verilator"):
            with patch("subprocess.run") as mock_run:
                mock_result = MagicMock()
                mock_result.returncode = 1
                mock_result.stderr = "Verilator build error"
                mock_run.return_value = mock_result
                with pytest.raises(VerilatorError, match="Verilator build failed"):
                    build_simulation(
                        rtl_paths=[dummy_v],
                        top_module="top",
                        output_dir=tmp_dir
                    )


class TestRunSimulation:
    def test_executable_not_found(self, tmp_dir):
        """If the simulation executable does not exist, subprocess raises FileNotFoundError
        which should propagate up or be handled. We'll test run_simulation's error handling
        for a missing file by letting subprocess.run fail."""
        fake_exe = tmp_dir / "fake_exe"
        vcd_path = tmp_dir / "out.vcd"
        with patch("subprocess.run", side_effect=FileNotFoundError("No such file")):
            with pytest.raises(FileNotFoundError):
                run_simulation(
                    sim_exe=fake_exe,
                    vcd_path=vcd_path,
                    cycles=10
                )

    def test_simulation_timeout(self, tmp_dir):
        """If the simulation times out, VerilatorError is raised."""
        fake_exe = tmp_dir / "fake_exe"
        fake_exe.write_text("")
        fake_exe.chmod(0o755)  # make it executable so subprocess can attempt
        vcd_path = tmp_dir / "out.vcd"
        with patch("subprocess.run", side_effect=TimeoutError("timed out")):
            # The actual exception is subprocess.TimeoutExpired, but we can mock with TimeoutError
            # The code catches subprocess.TimeoutExpired specifically; we can use that.
            import subprocess
            with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(
                cmd=["fake_exe"], timeout=300, output=b"", stderr=b""
            )):
                with pytest.raises(VerilatorError, match="Simulation timed out"):
                    run_simulation(
                        sim_exe=fake_exe,
                        vcd_path=vcd_path,
                        cycles=10
                    )

    def test_simulation_failure(self, tmp_dir):
        """If the simulation exits with non‑zero code, VerilatorError is raised."""
        fake_exe = tmp_dir / "fake_exe"
        fake_exe.write_text("")
        fake_exe.chmod(0o755)
        vcd_path = tmp_dir / "out.vcd"
        with patch("subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 1
            mock_result.stderr = "simulation error"
            mock_run.return_value = mock_result
            with pytest.raises(VerilatorError, match="Simulation exited with code 1"):
                run_simulation(
                    sim_exe=fake_exe,
                    vcd_path=vcd_path,
                    cycles=10
                )

    def test_vcd_not_found_after_simulation(self, tmp_dir):
        """If simulation runs but no VCD is produced, an error is raised."""
        fake_exe = tmp_dir / "fake_exe"
        fake_exe.write_text("")
        fake_exe.chmod(0o755)
        vcd_path = tmp_dir / "out.vcd"
        with patch("subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_run.return_value = mock_result
            with pytest.raises(VerilatorError, match="VCD file not found"):
                run_simulation(
                    sim_exe=fake_exe,
                    vcd_path=vcd_path,
                    cycles=10
                )
