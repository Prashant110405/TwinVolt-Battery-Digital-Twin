"""Unit tests for BatteryPackModel Multi-Cell and Pack Scale Aggregator."""

import unittest

from src.domain.battery.value_objects import BatteryTopology
from src.models.aggregator.balancing_model import (
    PassiveBalancingConfig,
    PassiveBalancingModel,
)
from src.models.aggregator.pack_model import (
    BatteryPackModel,
    PackModelOutput,
)
from src.models.base import BatteryModel
from src.models.ecm.generic_ecm import GenericECMModel
from src.models.exceptions import (
    InvalidModelParametersError,
    ModelInitializationError,
)
from src.models.parameters.chemistry_defaults import (
    get_chemistry_default_ocv_model,
    get_chemistry_default_parameters,
)
from src.models.types import ModelInput, ModelMetadata


class TestBatteryPackModel(unittest.TestCase):
    """Test suite verifying multi-cell aggregation, series/parallel scaling, dispersion, and thermal hotspots."""

    def _create_cell_model(self, cell_idx: int) -> GenericECMModel:
        """Helper creating standard 1-RC ECM cell model."""
        meta = ModelMetadata(
            model_id=f"cell_{cell_idx}",
            name=f"Cell {cell_idx}",
            paradigm="ECM_1RC",
        )
        params = get_chemistry_default_parameters("NMC", nominal_capacity_ah=2.5)
        ocv = get_chemistry_default_ocv_model("NMC")
        return GenericECMModel(metadata=meta, parameters=params, ocv_model=ocv)

    def setUp(self) -> None:
        """Create 4S1P and 4S2P test pack models."""
        self.topo_4s1p = BatteryTopology(series_count=4, parallel_count=1)
        self.pack_4s1p = BatteryPackModel.from_cell_factory(
            metadata=ModelMetadata(model_id="pack_4s1p", name="4S1P Pack", paradigm="AGGREGATED_PACK"),
            topology=self.topo_4s1p,
            cell_factory=self._create_cell_model,
        )

        self.topo_4s2p = BatteryTopology(series_count=4, parallel_count=2)
        self.pack_4s2p = BatteryPackModel.from_cell_factory(
            metadata=ModelMetadata(model_id="pack_4s2p", name="4S2P Pack", paradigm="AGGREGATED_PACK"),
            topology=self.topo_4s2p,
            cell_factory=self._create_cell_model,
        )

    # --------------------------------------------------------------------------
    # 1. Protocol & Scaling Properties
    # --------------------------------------------------------------------------
    def test_battery_model_protocol_compliance(self) -> None:
        """Verify BatteryPackModel adheres to the BatteryModel protocol."""
        self.assertIsInstance(self.pack_4s1p, BatteryModel)
        self.assertEqual(self.pack_4s1p.topology.total_cells, 4)

    def test_homogeneous_4s1p_voltage_and_heat_scaling(self) -> None:
        """In a homogeneous 4S1P pack, pack voltage is exactly 4x single cell voltage."""
        self.pack_4s1p.initialize(soc_init=0.90, temperature_c=25.0)

        # Step single cell for reference
        ref_cell = self._create_cell_model(99)
        ref_cell.initialize(soc_init=0.90, temperature_c=25.0)
        cell_out = ref_cell.step(ModelInput(current_a=2.0, dt_s=1.0, ambient_temperature_c=25.0))

        # Step 4S1P pack under 2.0 A
        pack_out = self.pack_4s1p.step(ModelInput(current_a=2.0, dt_s=1.0, ambient_temperature_c=25.0))

        self.assertIsInstance(pack_out, PackModelOutput)
        self.assertAlmostEqual(pack_out.terminal_voltage_v, 4.0 * cell_out.terminal_voltage_v, places=4)
        self.assertAlmostEqual(pack_out.heat_generation_w, 4.0 * cell_out.heat_generation_w, places=4)
        self.assertEqual(pack_out.cell_voltage_delta_v, 0.0)

    def test_parallel_branch_current_sharing_4s2p(self) -> None:
        """In a 4S2P pack under 4.0 A load, each constituent cell experiences exactly 2.0 A."""
        self.pack_4s2p.initialize(soc_init=0.80, temperature_c=25.0)

        # Single cell at 2.0 A
        ref_cell = self._create_cell_model(99)
        ref_cell.initialize(soc_init=0.80, temperature_c=25.0)
        cell_out = ref_cell.step(ModelInput(current_a=2.0, dt_s=1.0, ambient_temperature_c=25.0))

        # Pack at 4.0 A (divided by 2 parallel branches -> 2.0 A per cell)
        pack_out = self.pack_4s2p.step(ModelInput(current_a=4.0, dt_s=1.0, ambient_temperature_c=25.0))

        self.assertAlmostEqual(pack_out.terminal_voltage_v, 4.0 * cell_out.terminal_voltage_v, places=4)

    # --------------------------------------------------------------------------
    # 2. Heterogeneous Cell Variations & Thermal Hotspots
    # --------------------------------------------------------------------------
    def test_cell_dispersion_and_hotspot_tracking(self) -> None:
        """Vector initialization with divergent SOCs and temperatures tracks min/max and hotspot."""
        soc_init = [0.95, 0.85, 0.90, 0.80]
        temp_init = [25.0, 32.0, 27.0, 24.0]  # Cell 1 is thermal hotspot (32 C)

        self.pack_4s1p.initialize(soc_init=soc_init, temperature_c=temp_init)

        pack_out = self.pack_4s1p.step(ModelInput(current_a=1.0, dt_s=1.0, ambient_temperature_c=25.0))

        # Check dispersion metrics
        self.assertGreater(pack_out.cell_voltage_delta_v, 0.05)
        self.assertEqual(pack_out.max_cell_temperature_c, pack_out.cell_outputs[1].state.temperature_c)
        self.assertAlmostEqual(pack_out.max_cell_temperature_c, 31.86, places=1)

    # --------------------------------------------------------------------------
    # 3. Passive Cell Balancing Integration
    # --------------------------------------------------------------------------
    def test_passive_balancing_during_pack_charge(self) -> None:
        """During charging, highest cell above threshold draws bypass current."""
        # Custom balancing model: threshold 4.0 V, delta 20 mV
        bm = PassiveBalancingModel(
            PassiveBalancingConfig(bleed_resistance_ohm=20.0, voltage_threshold_v=4.0, voltage_delta_threshold_v=0.02)
        )
        pack_bal = BatteryPackModel.from_cell_factory(
            metadata=ModelMetadata(model_id="pack_bal", name="Balancing Pack", paradigm="AGGREGATED_PACK"),
            topology=self.topo_4s1p,
            cell_factory=self._create_cell_model,
            balancing_model=bm,
        )

        # Cell 0 has high SOC (0.95), others have 0.70
        pack_bal.initialize(soc_init=[0.95, 0.70, 0.70, 0.70], temperature_c=25.0)

        # Charge step: I = -2.0 A
        pack_out = pack_bal.step(ModelInput(current_a=-2.0, dt_s=1.0, ambient_temperature_c=25.0))

        # Cell 0 should have active bleed current
        self.assertGreater(pack_out.balancing_currents_a[0], 0.1)
        self.assertEqual(pack_out.balancing_currents_a[1], 0.0)
        # Total heat includes balancing dissipation
        self.assertGreater(pack_out.total_heat_generation_w, sum(o.heat_generation_w for o in pack_out.cell_outputs))

    # --------------------------------------------------------------------------
    # 4. Input & Topology Invariants
    # --------------------------------------------------------------------------
    def test_mismatched_cell_count_raises(self) -> None:
        """Providing wrong number of cells for topology must raise InvalidModelParametersError."""
        topo = BatteryTopology(series_count=4, parallel_count=1)
        cells = [self._create_cell_model(i) for i in range(3)]  # 3 cells instead of 4

        with self.assertRaises(InvalidModelParametersError):
            BatteryPackModel(
                metadata=ModelMetadata(model_id="bad", name="Bad Pack", paradigm="AGGREGATED_PACK"),
                topology=topo,
                cell_models=cells,
            )

    def test_vector_initialization_length_mismatch_raises(self) -> None:
        """Initializing with mismatched SOC vector length must raise ModelInitializationError."""
        with self.assertRaises(ModelInitializationError):
            self.pack_4s1p.initialize(soc_init=[0.9, 0.8])  # 2 elements instead of 4


if __name__ == "__main__":
    unittest.main()
