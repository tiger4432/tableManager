import pytest
from utils.physical_wafer_engine import PhysicalWaferEngine

def test_physical_wafer_engine_defaults():
    engine = PhysicalWaferEngine(
        wafer_diameter_mm=300.0,
        chip_size_x_mm=2.5,
        chip_size_y_mm=2.5,
        edge_exclusion_mm=3.0,
        offset_x_mm=0.0,
        offset_y_mm=0.0
    )
    
    assert engine.effective_radius_mm == 147.0
    cols, rows = engine.calculate_grid_dimensions()
    assert cols > 10
    assert rows > 10
    assert cols % 2 == 1  # Symmetric odd dimensions
    assert rows % 2 == 1

def test_physical_wafer_engine_centering_offset():
    # Symmetric 0 offset
    engine_zero = PhysicalWaferEngine(
        wafer_diameter_mm=200.0,
        chip_size_x_mm=10.0,
        chip_size_y_mm=10.0,
        edge_exclusion_mm=0.0,
        offset_x_mm=0.0,
        offset_y_mm=0.0
    )
    cols, rows = engine_zero.calculate_grid_dimensions()
    mask_zero = engine_zero.generate_wafer_mask(cols, rows)
    
    # Offset X +5.0mm
    engine_offset = PhysicalWaferEngine(
        wafer_diameter_mm=200.0,
        chip_size_x_mm=10.0,
        chip_size_y_mm=10.0,
        edge_exclusion_mm=0.0,
        offset_x_mm=5.0,
        offset_y_mm=0.0
    )
    mask_offset = engine_offset.generate_wafer_mask(cols, rows)
    
    # Verify that the offset mask differs from zero offset mask at the borders
    assert mask_zero != mask_offset

def test_physical_wafer_engine_to_dict():
    engine = PhysicalWaferEngine(
        wafer_diameter_mm=150.0,
        chip_size_x_mm=3.0,
        chip_size_y_mm=4.0,
        edge_exclusion_mm=2.0,
        offset_x_mm=0.5,
        offset_y_mm=-0.5
    )
    d = engine.to_dict()
    assert d["wafer_diameter_mm"] == 150.0
    assert d["chip_size_x_mm"] == 3.0
    assert d["chip_size_y_mm"] == 4.0
    assert d["edge_exclusion_mm"] == 2.0
    assert d["offset_x_mm"] == 0.5
    assert d["offset_y_mm"] == -0.5
    assert d["effective_radius_mm"] == 73.0
