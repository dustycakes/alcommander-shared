"""
alcommander-shared/zebra-print/engine.py

ZPLBuilder — Dynamic ZPL label generation with per-label font scaling,
template registry with versioning, and batch printing to Zebra printers.

Usage:
    from engine import ZPLBuilder, PrinterTransport, TemplateRegistry

    registry = TemplateRegistry("/path/to/zebra-templates")
    transport = PrinterTransport(host="192.168.1.100", port=9100)

    builder = ZPLBuilder(registry, transport)

    # Build and print a batch of labels
    items = [
        {"sku": "70-11160-0990", "qty": 42, "description": "TUBE, 1.000x1.500x.120"},
        {"sku": "70-11162-1010", "qty": 18, "description": "ANGLE, 2.000x2.000x.125"},
    ]
    results = builder.print_batch(items, template="bunk_label")
"""

import re
import json
import socket
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


# ─── Font Metrics (approximate for Zebra A0N/A0B scalable fonts at 203 DPI) ───
# Character width as fraction of point height. Rough but functional.
# Zebra's ^A0N (normal) and ^A0B (bold) have different aspect ratios.
_FONT_ASPECT = {
    "N": 0.6,   # Normal: char width ≈ 0.6 × height
    "B": 1.2,   # Bold: char width ≈ 1.2 × height
}


# ─── Template Registry ───────────────────────────────────────────────────────

@dataclass
class TemplateField:
    """Defines a scalable field within a label template."""
    name: str                # Logical name: "sku", "description", "qty", "date"
    x: int                   # X coordinate (dots) — top-left of field
    y: int                   # Y coordinate (dots)
    rotation: str = "N"      # N, R, I, B (Normal, Rotated, Inverted, Bottom-up)
    min_font_h: int = 20     # Minimum font height (dots)
    max_font_h: int = 200    # Maximum font height (dots)
    max_width: int = 800     # Maximum field width (dots) — prevents overflow
    max_lines: int = 1       # Max lines for ^FB wrapping (1 = single line)
    line_spacing: int = 2    # Line spacing for ^FB (dots)
    alignment: str = "L"     # Text alignment: L, C, R (for ^FB)
    is_barcode: bool = False # True if this is a barcode field (^BC)
    barcode_orientation: str = "N"  # Barcode rotation (for ^BC)


@dataclass
class TemplateSpec:
    """Full specification of a label template."""
    name: str                      # Template identifier (e.g., "bunk_label")
    version: str                   # Version string (e.g., "1.0", "2026-04-06")
    label_width: int               # Label width in dots (e.g., 609 for 3" @ 203 DPI)
    label_height: int              # Label height in dots (e.g., 1218 for 6" @ 203 DPI)
    fields: List[TemplateField]    # Scalable text/barcode fields
    static_zpl: str = ""           # Raw ZPL for static elements (lines, boxes, barcodes)
    source_file: str = ""          # Original .prn/.zpl filename for reference


class TemplateRegistry:
    """
    Manages multiple label templates with versioning.

    Templates are loaded from disk or defined programmatically.
    Each template has a version string for tracking changes.
    """

    def __init__(self, template_dir: Optional[str | Path] = None):
        self._template_dir = Path(template_dir) if template_dir else None
        self._templates: Dict[str, TemplateSpec] = {}

    def register(self, spec: TemplateSpec):
        """Register a template specification."""
        self._templates[spec.name] = spec
        logger.info(f"Registered template: {spec.name} v{spec.version}")

    def get(self, name: str) -> TemplateSpec:
        """Get a template by name. Raises KeyError if not found."""
        if name not in self._templates:
            # Try loading from file if dir is configured
            if self._template_dir:
                self._load_from_file(name)
            else:
                raise KeyError(f"Template '{name}' not found. Register it first or set template_dir.")
        return self._templates[name]

    def list_templates(self) -> Dict[str, str]:
        """Return {name: version} for all registered templates."""
        return {name: spec.version for name, spec in self._templates.items()}

    def load_zpl_file(self, name: str, filename: str, version: str = "1.0") -> str:
        """
        Load a raw .zpl/.prn file and register it as a static template.
        Use this when the template has no dynamic scaling needed.

        Returns the raw ZPL string.
        """
        if not self._template_dir:
            raise RuntimeError("Template directory not set.")

        zpl_path = self._template_dir / filename
        zpl = zpl_path.read_text(encoding="utf-8")

        spec = TemplateSpec(
            name=name,
            version=version,
            label_width=812,    # Default — override in register() if needed
            label_height=1218,
            fields=[],
            static_zpl=zpl,
            source_file=filename,
        )
        self.register(spec)
        return zpl

    def _load_from_file(self, name: str):
        """Auto-load a template from a JSON spec file if it exists."""
        spec_path = self._template_dir / f"{name}.json"
        if spec_path.exists():
            data = json.loads(spec_path.read_text())
            fields = [TemplateField(**f) for f in data.get("fields", [])]
            spec = TemplateSpec(
                name=data["name"],
                version=data.get("version", "1.0"),
                label_width=data["label_width"],
                label_height=data["label_height"],
                fields=fields,
                static_zpl=data.get("static_zpl", ""),
                source_file=data.get("source_file", ""),
            )
            self.register(spec)


# ─── ZPL Builder ─────────────────────────────────────────────────────────────

class ZPLBuilder:
    """
    Builds ZPL labels with dynamic font scaling per label.

    For each label, calculates the largest font size that fits
    the designated field box, applying ^FB wrapping where needed.
    """

    def __init__(self, registry: TemplateRegistry, dpi: int = 203):
        self.registry = registry
        self.dpi = dpi
        self._label_cache: List[str] = []  # Accumulated labels for batch

    def _calc_font_size(self, text: str, field_def: TemplateField) -> tuple[int, int]:
        """
        Calculate the largest font (height, width) that fits text
        within the field's max_width constraint.

        For multi-line (^FB max_lines > 1), text can wrap.
        For single-line, font must shrink to fit on one line.

        Returns: (font_height, font_width) — width = height for proportional
        """
        if not text:
            return (field_def.min_font_h, field_def.min_font_h)

        rotation = field_def.rotation
        aspect = _FONT_ASPECT.get(rotation, 0.6)
        max_h = field_def.max_font_h
        min_h = field_def.min_font_h
        max_w = field_def.max_width

        # For barcode fields, font scaling doesn't apply — return max
        if field_def.is_barcode:
            return (max_h, max_h)

        # Multi-line with ^FB wrapping
        if field_def.max_lines > 1:
            # Average characters per line at max font
            chars_per_line = max(1, int(max_w / (max_h * aspect)))
            lines_needed = max(1, len(text) / chars_per_line)

            if lines_needed <= field_def.max_lines:
                return (max_h, max_h)

            # Shrink font so text fits in max_lines
            chars_per_line_needed = len(text) / field_def.max_lines
            needed_height = int(max_w / chars_per_line_needed / aspect)
            font_h = max(min_h, min(max_h, needed_height))
            return (font_h, font_h)

        # Single line — shrink font to fit
        chars = len(text)
        needed_width = chars * max_h * aspect

        if needed_width <= max_w:
            return (max_h, max_h)

        # Calculate font height that makes text exactly max_w wide
        font_h = int(max_w / (chars * aspect))
        font_h = max(min_h, min(max_h, font_h))
        return (font_h, font_h)

    def _build_field_zpl(self, text: str, field_def: TemplateField) -> str:
        """
        Build ZPL commands for a single field with dynamic scaling.
        """
        if field_def.is_barcode:
            # Barcode fields don't scale — use static ^BC
            return f"^FO{field_def.x},{field_def.y}^BC{field_def.barcode_orientation},,,^FD{text}^FS"

        font_h, font_w = self._calc_font_size(text, field_def)
        rotation = field_def.rotation

        # ^A0N,h,w — scalable font
        # ^FB — field block for wrapping
        if field_def.max_lines > 1:
            return (
                f"^FO{field_def.x},{field_def.y}"
                f"^A0{rotation},{font_h},{font_w}"
                f"^FB{field_def.max_width},{field_def.max_lines},{field_def.line_spacing},{field_def.alignment}"
                f"^FD{text}^FS"
            )
        else:
            return (
                f"^FO{field_def.x},{field_def.y}"
                f"^A0{rotation},{font_h},{font_w}"
                f"^FD{text}^FS"
            )

    def build_label(self, data: Dict[str, Any], template: str = "bunk_label") -> str:
        """
        Build a single ZPL label from data dict and template name.

        Args:
            data: Dict of field_name → value (e.g., {"sku": "...", "qty": 42, ...})
            template: Template name from registry

        Returns:
            Complete ZPL string for one label
        """
        spec = self.registry.get(template)

        # Start with ^XA
        zpl = "^XA\n"

        # Add static ZPL (boxes, lines, fixed elements)
        if spec.static_zpl:
            # Strip ^XA/^XZ wrapper if present — we provide our own
            cleaned = spec.static_zpl.strip()
            if cleaned.startswith("^XA"):
                cleaned = cleaned[3:]
            if cleaned.endswith("^XZ"):
                cleaned = cleaned[:-3]
            zpl += cleaned + "\n"

        # Build dynamic fields
        for field_def in spec.fields:
            value = data.get(field_def.name, "")
            if value is None:
                value = ""
            value = str(value)
            zpl += self._build_field_zpl(value, field_def) + "\n"

        # Close label
        zpl += "^XZ\n"
        return zpl

    def build_batch(self, items: List[Dict[str, Any]], template: str = "bunk_label") -> str:
        """
        Build a batch of labels into a single ZPL string.

        Each item gets unique font scaling.
        Items are concatenated for efficient single-network send.

        Args:
            items: List of dicts, each with field data for one label
            template: Template name from registry

        Returns:
            Concatenated ZPL for all labels
        """
        labels = []
        for item in items:
            labels.append(self.build_label(item, template))
        return "".join(labels)

    def preview(self, data: Dict[str, Any], template: str = "bunk_label") -> str:
        """
        Return ZPL as preview text (no printer communication).
        For display in Streamlit st.code() or web textarea.
        """
        return self.build_label(data, template)


# ─── Printer Transport ────────────────────────────────────────────────────────

@dataclass
class PrintResult:
    """Result of a print job."""
    success: bool
    message: str
    labels_sent: int = 0
    error: Optional[str] = None
    zpl_preview: Optional[str] = None  # For debug/preview


class PrinterTransport:
    """
    Sends ZPL to Zebra printers over network (port 9100).
    """

    def __init__(self, host: str, port: int = 9100, timeout: float = 10.0):
        self.host = host
        self.port = port
        self.timeout = timeout

    def send(self, zpl: str) -> PrintResult:
        """Send raw ZPL to the printer via TCP port 9100."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(self.timeout)
                sock.connect((self.host, self.port))
                sock.sendall(zpl.encode("utf-8"))
            logger.info(f"Sent {len(zpl)} bytes of ZPL to {self.host}:{self.port}")
            return PrintResult(
                success=True,
                message=f"Sent to {self.host}:{self.port}",
                zpl_preview=zpl,
            )
        except socket.timeout:
            return PrintResult(
                success=False,
                message=f"Connection timed out: {self.host}:{self.port}",
                zpl_preview=zpl,
            )
        except ConnectionRefusedError:
            return PrintResult(
                success=False,
                message=f"Connection refused: {self.host}:{self.port}",
                zpl_preview=zpl,
            )
        except OSError as e:
            return PrintResult(
                success=False,
                message=f"Network error: {e}",
                zpl_preview=zpl,
            )

    def check_connection(self) -> bool:
        """Test if the printer is reachable."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(3)
                result = sock.connect_ex((self.host, self.port))
                return result == 0
        except OSError:
            return False


# ─── Convenience Facade ──────────────────────────────────────────────────────
# Single entry point that wires builder + transport together.

class ZebraPrintService:
    """
    High-level facade. One object to handle everything.
    """

    def __init__(self, printer_host: str, printer_port: int = 9100,
                 template_dir: Optional[str | Path] = None, dpi: int = 203):
        self.registry = TemplateRegistry(template_dir)
        self.transport = PrinterTransport(printer_host, printer_port)
        self.builder = ZPLBuilder(self.registry, dpi)

    def register_template(self, spec: TemplateSpec):
        """Register a label template."""
        self.registry.register(spec)

    def load_template_file(self, name: str, filename: str, version: str = "1.0"):
        """Load a .zpl/.prn file from the template directory."""
        self.registry.load_zpl_file(name, filename, version)

    def print_label(self, data: Dict[str, Any], template: str = "bunk_label") -> PrintResult:
        """Build and print a single label."""
        zpl = self.builder.build_label(data, template)
        return self.transport.send(zpl)

    def print_batch(self, items: List[Dict[str, Any]], template: str = "bunk_label") -> List[PrintResult]:
        """
        Build and print a batch. Each item gets unique scaling,
        all sent as one ZPL stream.
        """
        zpl = self.builder.build_batch(items, template)
        return [self.transport.send(zpl)]  # One send for the whole batch

    def preview_label(self, data: Dict[str, Any], template: str = "bunk_label") -> str:
        """Return ZPL text for preview (no printer)."""
        return self.builder.preview(data, template)

    def printer_online(self) -> bool:
        """Check if printer is reachable."""
        return self.transport.check_connection()
