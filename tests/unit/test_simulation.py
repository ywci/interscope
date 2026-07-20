# tests/unit/test_simulation.py
#
# Unit tests for the high-level simulation orchestrator (revised).
# Verifies that simulate_design calls the consolidated
# koika_to_rtl synthesis pass, the Verilator backend, and
# optionally generates assertion files.

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from specir.dialects import spec_ir
from specir.verification.simulation import simulate_design, SimulationError


def _make_spec_module(name="test"):
    """Create a minimal SpecModule for testing."""
    state_ops = [
        spec_ir.SpecStateOp(state_name="cnt", kind="register", data_type="bits<8>", initial=0)
    ]
    rule_ops = [
        spec_ir.SpecRuleOp(rule_name="inc", condition="true",
                           actions=["(write cnt (add (read cnt) 1))"])
    ]
    return spec_ir.SpecModule(name=name, state_ops=state_ops, rule_ops=rule_ops)


class TestSimulateDesign:
    def test_success(self, tmp_path):
        """A full simulation should succeed and return the VCD path."""
        spec_mod = _make_spec_module()
        vcd_path = tmp_path / "traces" / "test.vcd"
        vcd_path.parent.mkdir(parents=True, exist_ok=True)

        # Create a dummy RTL file so the existence check passes
        rtl_file = tmp_path / "rtl" / "test.v"
        rtl_file.parent.mkdir(parents=True, exist_ok=True)
        rtl_file.write_text("// dummy")

        # Mock the synthesis pass and the Verilator simulation
        with patch("specir.verification.simulation.koika_to_rtl.convert") as mock_rtl, \
             patch("specir.verification.simulation.verilator_sim.simulate") as mock_sim:

            mock_rtl.return_value = MagicMock()
            mock_rtl.return_value.top_module.file_path = rtl_file
            mock_sim.return_value = vcd_path

            result = simulate_design(
                spec_module=spec_mod,
                output_dir=tmp_path,
                cycles=10,
            )

            # Verify the synthesis pass was called with the SpecModule
            mock_rtl.assert_called_once()
            mock_sim.assert_called_once()
            assert result == vcd_path

    def test_synthesis_fails(self, tmp_path):
        """If koika_to_rtl.convert raises, a SimulationError is raised."""
        spec_mod = _make_spec_module()
        with patch("specir.verification.simulation.koika_to_rtl.convert",
                   side_effect=RuntimeError("synthesis error")):
            with pytest.raises(SimulationError, match="Kōika synthesis failed"):
                simulate_design(spec_mod, output_dir=tmp_path)

    def test_verilator_sim_fails(self, tmp_path):
        """If verilator_sim.simulate raises, a SimulationError is raised."""
        spec_mod = _make_spec_module()
        rtl_file = tmp_path / "rtl" / "test.v"
        rtl_file.parent.mkdir(parents=True, exist_ok=True)
        rtl_file.write_text("// dummy")

        with patch("specir.verification.simulation.koika_to_rtl.convert") as mock_rtl, \
             patch("specir.verification.simulation.verilator_sim.simulate",
                   side_effect=RuntimeError("verilator crash")):
            mock_rtl.return_value = MagicMock()
            mock_rtl.return_value.top_module.file_path = rtl_file
            with pytest.raises(SimulationError, match="Verilator simulation failed"):
                simulate_design(spec_mod, output_dir=tmp_path)

    def test_default_output_dir(self, tmp_path):
        """If output_dir is not given, it should default to build/<design>/sim."""
        spec_mod = _make_spec_module()
        vcd = tmp_path / "traces" / "test.vcd"
        vcd.parent.mkdir(parents=True)

        rtl_file = tmp_path / "build" / "test" / "sim" / "rtl" / "test.v"
        rtl_file.parent.mkdir(parents=True, exist_ok=True)
        rtl_file.write_text("// dummy")

        config = {
            "directories": {"build": "build"},
            "verification": {"simulation_cycles": 1000}
        }

        with patch("specir.verification.simulation.koika_to_rtl.convert") as mock_rtl, \
             patch("specir.verification.simulation.verilator_sim.simulate",
                   return_value=vcd) as mock_sim, \
             patch("specir.verification.simulation.get_project_root",
                   return_value=tmp_path):
            mock_rtl.return_value = MagicMock()
            mock_rtl.return_value.top_module.file_path = rtl_file

            result = simulate_design(spec_module=spec_mod, config=config)
            assert result == vcd

    def test_cycles_from_config(self, tmp_path):
        """If cycles is not given, the config default is used."""
        spec_mod = _make_spec_module()
        vcd = tmp_path / "traces" / "test.vcd"
        vcd.parent.mkdir(parents=True)

        rtl_file = tmp_path / "rtl" / "test.v"
        rtl_file.parent.mkdir(parents=True, exist_ok=True)
        rtl_file.write_text("// dummy")

        config = {
            "directories": {"build": "build"},
            "verification": {"simulation_cycles": 555}
        }

        with patch("specir.verification.simulation.koika_to_rtl.convert") as mock_rtl, \
             patch("specir.verification.simulation.verilator_sim.simulate",
                   return_value=vcd) as mock_sim, \
             patch("specir.verification.simulation.get_config",
                   return_value=555):
            mock_rtl.return_value = MagicMock()
            mock_rtl.return_value.top_module.file_path = rtl_file

            simulate_design(spec_module=spec_mod, output_dir=tmp_path, config=config)
            call_args = mock_sim.call_args[1]
            assert call_args["cycles"] == 555

    def test_rtl_not_found_raises_error(self, tmp_path):
        """If the generated RTL file does not exist, a SimulationError is raised."""
        spec_mod = _make_spec_module()
        with patch("specir.verification.simulation.koika_to_rtl.convert") as mock_rtl:
            mock_container = MagicMock()
            mock_container.top_module.file_path = tmp_path / "nonexistent.v"
            mock_rtl.return_value = mock_container
            with pytest.raises(SimulationError, match="Verilog file not found"):
                simulate_design(spec_mod, output_dir=tmp_path)

    def test_assertion_generation_called(self, tmp_path):
        """When assert_lang is provided, _generate_assertions is called."""
        spec_mod = _make_spec_module()
        vcd_path = tmp_path / "traces" / "test.vcd"
        vcd_path.parent.mkdir(parents=True, exist_ok=True)

        rtl_file = tmp_path / "rtl" / "test.v"
        rtl_file.parent.mkdir(parents=True, exist_ok=True)
        rtl_file.write_text("// dummy")

        with patch("specir.verification.simulation.koika_to_rtl.convert") as mock_rtl, \
             patch("specir.verification.simulation.verilator_sim.simulate") as mock_sim, \
             patch("specir.verification.simulation._generate_assertions") as mock_gen:

            mock_rtl.return_value = MagicMock()
            mock_rtl.return_value.top_module.file_path = rtl_file
            mock_sim.return_value = vcd_path

            result = simulate_design(
                spec_module=spec_mod,
                output_dir=tmp_path,
                cycles=10,
                assert_lang="sva",
            )

            # Assertions should be generated with correct parameters
            mock_gen.assert_called_once_with(spec_mod, "sva", tmp_path)
            # Simulation should still succeed
            assert result == vcd_path

    def test_assertion_generation_not_called_by_default(self, tmp_path):
        """Without assert_lang, _generate_assertions is not called."""
        spec_mod = _make_spec_module()
        vcd_path = tmp_path / "traces" / "test.vcd"
        vcd_path.parent.mkdir(parents=True, exist_ok=True)

        rtl_file = tmp_path / "rtl" / "test.v"
        rtl_file.parent.mkdir(parents=True, exist_ok=True)
        rtl_file.write_text("// dummy")

        with patch("specir.verification.simulation.koika_to_rtl.convert") as mock_rtl, \
             patch("specir.verification.simulation.verilator_sim.simulate") as mock_sim, \
             patch("specir.verification.simulation._generate_assertions") as mock_gen:

            mock_rtl.return_value = MagicMock()
            mock_rtl.return_value.top_module.file_path = rtl_file
            mock_sim.return_value = vcd_path

            simulate_design(
                spec_module=spec_mod,
                output_dir=tmp_path,
                cycles=10,
            )

            # The function should not be called
            mock_gen.assert_not_called()
