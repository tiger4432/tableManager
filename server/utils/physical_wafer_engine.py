import math
from typing import Dict, List, Tuple, Any

class PhysicalWaferEngine:
    """
    Physical Wafer Geometry & Centering Engine.
    Calculates 2D wafer grid layout, effective radius, cell physical coordinates (mm),
    and valid wafer inclusion masks based on SEMI standard wafer parameters.
    """
    def __init__(
        self,
        wafer_diameter_mm: float = 300.0,
        chip_size_x_mm: float = 2.5,
        chip_size_y_mm: float = 2.5,
        edge_exclusion_mm: float = 3.0,
        offset_x_mm: float = 0.0,
        offset_y_mm: float = 0.0
    ):
        self.wafer_diameter_mm = float(wafer_diameter_mm)
        self.chip_size_x_mm = max(0.1, float(chip_size_x_mm))
        self.chip_size_y_mm = max(0.1, float(chip_size_y_mm))
        self.edge_exclusion_mm = max(0.0, float(edge_exclusion_mm))
        self.offset_x_mm = float(offset_x_mm)
        self.offset_y_mm = float(offset_y_mm)
        
        self.effective_radius_mm = max(0.0, (self.wafer_diameter_mm / 2.0) - self.edge_exclusion_mm)

    def calculate_grid_dimensions(self) -> Tuple[int, int]:
        """
        Calculates optimal grid columns and rows based on physical wafer size and chip pitch.
        """
        if self.chip_size_x_mm <= 0 or self.chip_size_y_mm <= 0:
            return 10, 10
        
        cols = math.ceil((2.0 * self.effective_radius_mm) / self.chip_size_x_mm) + 2
        rows = math.ceil((2.0 * self.effective_radius_mm) / self.chip_size_y_mm) + 2
        
        # Ensure odd symmetry bounds for clean centering
        if cols % 2 == 0:
            cols += 1
        if rows % 2 == 0:
            rows += 1
            
        return max(5, cols), max(5, rows)

    def get_cell_physical_mm(self, c: int, r: int, cols: int, rows: int) -> Tuple[float, float]:
        """
        Returns physical (x_mm, y_mm) coordinates of cell center relative to wafer center (0,0).
        """
        center_c = (cols - 1) / 2.0
        center_r = (rows - 1) / 2.0
        
        x_mm = (c - center_c) * self.chip_size_x_mm + self.offset_x_mm
        y_mm = (center_r - r) * self.chip_size_y_mm + self.offset_y_mm
        return x_mm, y_mm

    def is_cell_inside_wafer(self, c: int, r: int, cols: int, rows: int) -> bool:
        """
        Determines if a cell is COMPLETELY inside the effective wafer radius.
        All 4 corners of the chip cell must be <= effective_radius_mm.
        """
        if self.effective_radius_mm <= 0:
            return False
            
        cx_mm, cy_mm = self.get_cell_physical_mm(c, r, cols, rows)
        half_w = self.chip_size_x_mm / 2.0
        half_h = self.chip_size_y_mm / 2.0
        radius_sq = self.effective_radius_mm * self.effective_radius_mm
        
        corners = [
            (cx_mm - half_w, cy_mm - half_h),
            (cx_mm + half_w, cy_mm - half_h),
            (cx_mm - half_w, cy_mm + half_h),
            (cx_mm + half_w, cy_mm + half_h),
        ]
        
        for x, y in corners:
            if (x * x + y * y) > radius_sq:
                return False
                
        return True

    def generate_wafer_mask(self, cols: int = None, rows: int = None) -> List[List[bool]]:
        """
        Generates a 2D boolean mask [rows][cols] of valid wafer cells.
        """
        if cols is None or rows is None:
            cols, rows = self.calculate_grid_dimensions()
            
        mask = []
        for r in range(rows):
            row_mask = []
            for c in range(cols):
                row_mask.append(self.is_cell_inside_wafer(c, r, cols, rows))
            mask.append(row_mask)
        return mask

    def to_dict(self) -> Dict[str, Any]:
        """
        Returns a dictionary representation of physical parameters for metadata serialization.
        """
        return {
            "wafer_diameter_mm": self.wafer_diameter_mm,
            "chip_size_x_mm": self.chip_size_x_mm,
            "chip_size_y_mm": self.chip_size_y_mm,
            "edge_exclusion_mm": self.edge_exclusion_mm,
            "offset_x_mm": self.offset_x_mm,
            "offset_y_mm": self.offset_y_mm,
            "effective_radius_mm": self.effective_radius_mm
        }
