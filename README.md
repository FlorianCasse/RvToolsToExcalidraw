# DrawMyInfra

Convert VMware infrastructure exports into ready-to-open [Excalidraw](https://excalidraw.com) diagrams — directly in your browser, no server required.

**Live app:** https://floriancasse.github.io/DrawMyInfra/

---

## Supported sources

| Tool | Format | Sheets used |
|---|---|---|
| [RVTools](https://www.robware.net/rvtools/) | `.xlsx` | `vHost`, `vSource` |
| [LiveOptics](https://www.liveoptics.com/) | `.xlsx` | `ESX Hosts`, `ESX Performance` |

The app auto-detects the format — just drop any supported file and it works.

---

## What it does

Upload one or more exports (mix and match sources) and get a colour-coded diagram showing your VMware infrastructure: sites, clusters, and hosts — each with model, ESXi version, service tag, VM count, CPU and memory utilisation.

Multiple sites are laid out side by side, each assigned a distinct colour palette.

---

## Usage

1. Open the [live app](https://floriancasse.github.io/DrawMyInfra)
2. Drop one or more `.xlsx` files onto the upload area
3. Optionally rename each site
4. Click **Generate Diagram**
5. Preview the diagram live on the page
6. Click **Download .excalidraw** and open it at [excalidraw.com](https://excalidraw.com)

---

## Running locally (optional)

A Flask version (`app.py`) is included for local use.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Then open http://localhost:5000.

---

## Tech stack

- Vanilla HTML/CSS/JS — no build step
- [SheetJS](https://sheetjs.com/) for `.xlsx` parsing in the browser
- [@excalidraw/excalidraw](https://www.npmjs.com/package/@excalidraw/excalidraw) for the embedded diagram viewer
- GitHub Pages for hosting

---

Built with ♥ by Florian Casse
