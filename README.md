# alcommander-shared

Shared components and utilities across Alcommander projects.

## Structure

```
alcommander-shared/
├── zebra-print/          # Zebra print engine
│   ├── engine.py         # ZPLBuilder + TemplateRegistry + PrinterTransport + ZebraPrintService
│   ├── templates/        # .zpl/.prn label template files
│   └── README.md         # Usage docs
├── theme-tokens/         # Shared design tokens (future)
│   └── dark-mode.css     # Color palette, spacing, typography
└── README.md             # This file
```

## Current Components

### zebra-print (Active)
Dynamic ZPL label builder with per-label font scaling, template registry with versioning, and batch TCP printing to port 9100.

**Key classes:**
- `ZPLBuilder` — Builds ZPL with dynamic `^A0N,H,W` font scaling per label
- `TemplateRegistry` — Manages multiple templates with version tracking
- `PrinterTransport` — Sends ZPL via TCP socket to port 9100
- `ZebraPrintService` — Facade that wires all three together

**Consumed by:** Manifest-to-LabelLIVE (primary), Kanban-Pulse (future)

## Usage

Each project imports by relative path:

```python
import sys
sys.path.insert(0, '../alcommander-shared/zebra-print')
from engine import ZebraPrintService
```

## Adding New Shared Components

1. Create module directory under `alcommander-shared/`
2. Write README with usage docs
3. Update this file
4. Update consuming projects' import paths
5. Log in `intel/DAILY-INTEL.md`
