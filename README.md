# DrawMyInfra

Convert VMware infrastructure exports into ready-to-open [Excalidraw](https://excalidraw.com) diagrams — directly in your browser, no server required.

**Live app (production):** https://floriancasse.github.io/DrawMyInfra/
**Dev preview:** https://floriancasse.github.io/DrawMyInfra/dev/

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

### VCF 9 Compatibility Check

Tick the **Check VCF 9 Compatibility** checkbox before generating to check each host against the [Broadcom Compatibility Guide](https://compatibilityguide.broadcom.com/) and annotate it with a readiness indicator:

| Indicator | Meaning |
|---|---|
| ✅ VCF 9.0 + 9.1 Ready | Server model supports both ESXi 9.0 and 9.1 |
| ✅ VCF 9.0 Ready | Server model supports ESXi 9.0 only |
| ❌ Not VCF9 Ready | Server model not found in the Compatibility Guide |
| ⚠️ VCF9 ? | Server model could not be determined |

Incompatible hosts are highlighted with a red border in the diagram.

---

## Usage

1. Open the [live app](https://floriancasse.github.io/DrawMyInfra) (or the [dev preview](https://floriancasse.github.io/DrawMyInfra/dev/))
2. Drop one or more `.xlsx` files onto the upload area
3. Optionally rename each site
4. Optionally tick **Check VCF 9 Compatibility** to add Broadcom Compatibility Guide readiness indicators
5. Click **Generate Diagram**
6. Preview the diagram live on the page
7. Click **Download .excalidraw** and open it at [excalidraw.com](https://excalidraw.com)

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
- [Broadcom Compatibility Guide](https://compatibilityguide.broadcom.com/) for VCF 9 compatibility data

---

## Deployment

A GitHub Actions workflow deploys both branches to GitHub Pages:

| Branch | URL |
|---|---|
| `main` | https://floriancasse.github.io/DrawMyInfra/ |
| `dev` | https://floriancasse.github.io/DrawMyInfra/dev/ |

Every push to either branch triggers a rebuild.

---

Built with ♥ by Florian Casse
