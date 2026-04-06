# Zebra Print Engine

Shared ZPL generation with **dynamic per-label font scaling**, template registry with versioning, and batch printing for Alcommander projects.

## Architecture

```
TemplateRegistry          ZPLBuilder              PrinterTransport
├── TemplateSpec          ├── _calc_font_size()    ├── send() — TCP port 9100
│   ├── fields[]          ├── _build_field_zpl()  ├── check_connection()
│   ├── static_zpl        ├── build_label()       └── (future: USB, file)
│   └── version           ├── build_batch()
└── load_zpl_file()       └── preview()
```

**Key concept:** The template defines the *layout geometry* (field positions, max widths, wrapping rules). The builder calculates the *largest font* that fits each field for each individual label. Every label in a batch gets unique scaling.

## Usage

### Quick Start

```python
from engine import (
    ZebraPrintService, TemplateSpec, TemplateField
)

# Wire up the service
service = ZebraPrintService(
    printer_host="192.168.1.100",
    printer_port=9100,
    template_dir="/path/to/zebra-templates",
)

# Register a template (one-time setup per template)
service.register_template(TemplateSpec(
    name="bunk_label",
    version="1.0",
    label_width=812,
    label_height=1218,
    fields=[
        TemplateField(name="sku", x=514, y=1218, rotation="B",
                      min_font_h=80, max_font_h=155, max_width=1212,
                      max_lines=1, alignment="C"),
        TemplateField(name="qty", x=733, y=1218, rotation="B",
                      min_font_h=100, max_font_h=176, max_width=807,
                      max_lines=1, alignment="R"),
        TemplateField(name="description", x=31, y=10, rotation="B",
                      min_font_h=60, max_font_h=113, max_width=1196,
                      max_lines=2, alignment="L"),
    ],
    static_zpl="""
        ^FO567,383^GB217,823,8^FS
        ^FO369,10^GB0,1192,8^FS
        ^FO688,196^GFA,1397,2004,12,:Z64:...^FS
        ^FO552,14^GB0,1192,8^FS
        ^FO671,363^BCB,,N,N,,A^FN1^FS
    """,
))

# Print a single label
result = service.print_label({
    "sku": "70-11160-0990",
    "qty": 42,
    "description": "TUBE, 1.000x1.500x.120",
}, template="bunk_label")

# Print a batch (one network send, unique scaling per label)
items = [
    {"sku": "70-11160-0990", "qty": 42, "description": "TUBE, 1.000x1.500x.120"},
    {"sku": "70-11162-1010", "qty": 18, "description": "ANGLE, 2.000x2.000x.125"},
    {"sku": "52-00000240", "qty": 96, "description": "FLAT BAR, 0.25x3.00"},
]
results = service.print_batch(items, template="bunk_label")
```

### Preview (No Printer)

```python
zpl = service.preview_label({
    "sku": "70-11160-0990",
    "qty": 42,
    "description": "TUBE, 1.000x1.500x.120",
})
st.code(zpl)  # Streamlit preview panel
```

### Check Printer Status

```python
if service.printer_online():
    st.success("Printer online")
else:
    st.error("Printer offline")
```

### Load Template from .prn/.zpl File

```python
# Loads raw ZPL as static elements (no dynamic fields)
service.load_template_file("bunk_label", "extrusion-label-template.prn", version="1.0")
```

## Template Versioning & Management

Templates evolve. The registry handles this:

```python
# Register a new version alongside the old
service.register_template(TemplateSpec(
    name="bunk_label",
    version="2.0",   # Added date field, adjusted positions
    ...
))

# Register a completely different template
service.register_template(TemplateSpec(
    name="bunk_label_with_date",
    version="1.0",
    ...
))

# See all registered templates
print(service.registry.list_templates())
# → {"bunk_label": "2.0", "bunk_label_with_date": "1.0"}
```

**Recommendation:** When a template changes, bump the version. The old version stays registered — existing code that references it keeps working. Update callers to use the new version when ready.

## Dynamic Font Scaling Logic

For each label, the builder:

1. **Reads the text** for each field (sku, description, etc.)
2. **Calculates character count** × font aspect ratio = required width
3. **If multi-line** (`max_lines > 1`): uses `^FB` wrapping, shrinks font so text fits in max lines
4. **If single-line**: shrinks font until text fits within `max_width`
5. **Emits `^A0N,h,w`** with the calculated size + `^FB` if wrapping
6. **Each label gets unique math** — short SKU = big font, long description = smaller font

### Constraints

| Parameter | Effect |
|---|---|
| `min_font_h` | Font never shrinks below this (readability floor) |
| `max_font_h` | Font never exceeds this (label boundary ceiling) |
| `max_width` | Field box width — text wraps or shrinks to fit |
| `max_lines` | Max `^FB` wrap lines (1 = no wrap, 2 = two-line max) |

## DPI

Default is **203 DPI** (Zebra ZD421). All coordinates are in dots.

```
3 inches × 203 DPI = 609 dots wide
6 inches × 203 DPI = 1218 dots tall
```

If using a different printer DPI, pass `dpi=300` (or whatever) to `ZPLBuilder` or `ZebraPrintService`.

## Projects Using This

| Project | Integration |
|---|---|
| **Manifest-to-LabelLIVE** | Primary consumer — replaces Excel/LABEL LIVE flow |
| **Kanban-Pulse** | Deferred — depends on evolved build requirements |
