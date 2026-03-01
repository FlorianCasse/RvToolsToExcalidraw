"""
DrawMyInfra — VMware infrastructure → Excalidraw Generator
Flask web app — single file, no templates directory needed.
Supports RVTools and LiveOptics .xlsx exports.
"""

import io
import json
import os
import uuid
import re
from flask import Flask, request, send_file, Response
import pandas as pd

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50 MB upload limit

# ─── Color Palette (up to 6 sites) ───────────────────────────────────────────
PALETTES = [
    {   # DrawMyInfra Teal — primary brand
        "zone_bg":    "#E3F5F4", "zone_stroke": "#2DC4B8",
        "hdr_bg":     "#2DC4B8", "hdr_text":    "#FFFFFF",
        "cluster_bg": "#EAF8F7", "cluster_stroke": "#2DC4B8",
        "host_bg":    "#FFFFFF", "host_stroke":  "#7DD4CE",
        "host_text":  "#0D4A45",
    },
    {   # ITQ Blue
        "zone_bg":    "#E8F0FB", "zone_stroke": "#1A5DAD",
        "hdr_bg":     "#1A5DAD", "hdr_text":    "#FFFFFF",
        "cluster_bg": "#EDF3FD", "cluster_stroke": "#1A5DAD",
        "host_bg":    "#FFFFFF", "host_stroke":  "#5B9BD5",
        "host_text":  "#0D3B78",
    },
    {   # ITQ Green (teal)
        "zone_bg":    "#E8F5EE", "zone_stroke": "#1E8449",
        "hdr_bg":     "#1E8449", "hdr_text":    "#FFFFFF",
        "cluster_bg": "#EDF7F1", "cluster_stroke": "#1E8449",
        "host_bg":    "#FFFFFF", "host_stroke":  "#52BE80",
        "host_text":  "#145A32",
    },
    {   # ITQ Indigo
        "zone_bg":    "#EDE8F7", "zone_stroke": "#5B3DAB",
        "hdr_bg":     "#5B3DAB", "hdr_text":    "#FFFFFF",
        "cluster_bg": "#F3F0FB", "cluster_stroke": "#5B3DAB",
        "host_bg":    "#FFFFFF", "host_stroke":  "#9B7DD4",
        "host_text":  "#3D2580",
    },
    {   # ITQ Slate
        "zone_bg":    "#EAF0F0", "zone_stroke": "#2E7D8C",
        "hdr_bg":     "#2E7D8C", "hdr_text":    "#FFFFFF",
        "cluster_bg": "#EEF4F5", "cluster_stroke": "#2E7D8C",
        "host_bg":    "#FFFFFF", "host_stroke":  "#6BB8C4",
        "host_text":  "#1A4D56",
    },
    {   # ITQ Crimson
        "zone_bg":    "#FAE8E8", "zone_stroke": "#C0392B",
        "hdr_bg":     "#C0392B", "hdr_text":    "#FFFFFF",
        "cluster_bg": "#FDF0F0", "cluster_stroke": "#C0392B",
        "host_bg":    "#FFFFFF", "host_stroke":  "#E57373",
        "host_text":  "#7B241C",
    },
]

# ─── Layout constants ─────────────────────────────────────────────────────────
ZONE_W      = 780   # width of each site zone
COLS        = 3     # hosts per row inside a cluster
HOST_W      = 230   # host box width
HOST_H      = 120   # host box height (5 lines)
CLUSTER_H   = 28    # cluster header height
HEADER_H    = 65    # site header height
PAD         = 12    # padding inside zones
COL_GAP     = 10    # gap between host columns
ROW_GAP     = 8     # gap between host rows
ZONE_GAP    = 30    # gap between site zones (horizontal)
CANVAS_X    = 60    # left margin
CANVAS_Y    = 60    # top margin


# ─── Helpers ──────────────────────────────────────────────────────────────────
def uid():
    return str(uuid.uuid4())


def find_col(df, candidates):
    """Return first column name from candidates that exists in df (case-insensitive)."""
    cols_lower = {c.lower(): c for c in df.columns}
    for c in candidates:
        if c.lower() in cols_lower:
            return cols_lower[c.lower()]
    return None


def safe(val):
    if pd.isna(val) or val is None:
        return ""
    return str(val).strip()


def fmt_pct(v):
    """Format a value as a rounded percentage string."""
    try:
        return f"{float(v):.0f}%"
    except (ValueError, TypeError):
        return str(v).strip() if v else "—"


# ─── VCF 9 Compatibility (Broadcom Compatibility Guide) ──────────────────────
_hcl_cache = None
_VENDOR_PREFIX_RE = re.compile(
    r'^(Dell\s+(Inc\.?\s*)?|HPE?\s+|Lenovo\s+|Cisco\s+|Fujitsu\s+)', re.I
)


def load_hcl():
    global _hcl_cache
    if _hcl_cache is not None:
        return _hcl_cache
    hcl_path = os.path.join(os.path.dirname(__file__), 'vcf9_hcl.json')
    with open(hcl_path, 'r') as f:
        _hcl_cache = json.load(f)
    return _hcl_cache


def build_vcf9_lookup(hcl_data):
    return {entry['m'].strip().lower(): entry['r'] for entry in hcl_data}


def normalize_model(model):
    return _VENDOR_PREFIX_RE.sub('', model).strip()


def _vcf9_label(releases):
    versions = sorted(r.replace('ESXi ', '') for r in releases)
    return '\u2705 VCF ' + ' + '.join(versions) + ' Ready'


def check_vcf9_compat(model, lookup):
    if not model:
        return {'status': 'unknown', 'label': '\u26A0\uFE0F VCF9 ?'}
    norm = normalize_model(model).lower()
    if norm in lookup:
        return {'status': 'compatible', 'label': _vcf9_label(lookup[norm])}
    for hcl_model, releases in lookup.items():
        if norm in hcl_model or hcl_model in norm:
            return {'status': 'compatible', 'label': _vcf9_label(releases)}
    return {'status': 'incompatible', 'label': '\u274C Not VCF9 Ready'}


def parse_rvtools(xls, site_name):
    """Parse an RVTools .xlsx file → structured dict."""
    sheet_names_lower = {s.lower(): s for s in xls.sheet_names}

    # ── vHost sheet ──
    vhost_sheet = sheet_names_lower.get("vhost")
    if vhost_sheet is None:
        raise ValueError(f"No vHost sheet found in {site_name}")

    vh = xls.parse(vhost_sheet, header=0)

    col_host    = find_col(vh, ["VM Host", "Host", "DNS Name", "Name"])
    col_cluster = find_col(vh, ["Cluster", "Cluster Name"])
    col_model   = find_col(vh, ["Model", "Hardware Model"])
    col_esxi    = find_col(vh, ["ESX Version", "ESXi Version", "Version"])
    col_vms     = find_col(vh, ["# VMs", "VMs", "Number of VMs", "#VMs"])
    col_cpu     = find_col(vh, ["CPU usage %", "CPU %", "CPU Usage %", "CPU%"])
    col_mem     = find_col(vh, ["Memory usage %", "Mem %", "Memory %", "Mem%"])
    col_svc     = find_col(vh, ["Service Tag", "Serial Number", "SN"])

    hosts = []
    for _, row in vh.iterrows():
        hostname = safe(row[col_host]) if col_host else ""
        if not hostname:
            continue
        cluster  = safe(row[col_cluster]) if col_cluster else "Default"
        model    = safe(row[col_model])   if col_model   else ""
        esxi     = safe(row[col_esxi])    if col_esxi    else ""
        vms      = safe(row[col_vms])     if col_vms     else ""
        cpu      = safe(row[col_cpu])     if col_cpu     else ""
        mem      = safe(row[col_mem])     if col_mem     else ""
        svc      = safe(row[col_svc])     if col_svc     else ""

        # Abbreviate ESXi version to major.minor.patch
        esxi_short = esxi
        m = re.search(r'(\d+\.\d+\.\d+)', esxi)
        if m:
            esxi_short = m.group(1)

        hosts.append({
            "hostname": hostname,
            "cluster":  cluster or "Default",
            "model":    model,
            "esxi":     esxi_short,
            "vms":      vms or "0",
            "cpu":      fmt_pct(cpu),
            "mem":      fmt_pct(mem),
            "svc":      svc,
        })

    # ── vSource sheet (vCenter version) ──
    vcenter_version = ""
    vsource_sheet = sheet_names_lower.get("vsource")
    if vsource_sheet:
        vs = xls.parse(vsource_sheet, header=0)
        col_fn = find_col(vs, ["Fullname", "Full Name", "Version", "Name"])
        if col_fn:
            for val in vs[col_fn].dropna():
                s = str(val).strip()
                m = re.search(r'vCenter Server\s+(\d+\.\d+\.\d+)', s, re.IGNORECASE)
                if not m:
                    m = re.search(r'(\d+\.\d+\.\d+\.\d+)', s)
                if m:
                    vcenter_version = m.group(1)
                    break

    # Group hosts by cluster
    clusters = {}
    for h in hosts:
        c = h["cluster"]
        clusters.setdefault(c, []).append(h)

    return {
        "site_name":       site_name,
        "clusters":        clusters,
        "vcenter_version": vcenter_version,
        "total_hosts":     len(hosts),
        "total_vms":       sum(int(h["vms"]) if h["vms"].isdigit() else 0 for h in hosts),
    }


def parse_liveoptics(xls, site_name):
    """Parse a LiveOptics .xlsx file → structured dict."""
    sheet_names_lower = {s.lower(): s for s in xls.sheet_names}

    hosts_sheet = sheet_names_lower.get("esx hosts")
    if hosts_sheet is None:
        raise ValueError(f"No 'ESX Hosts' sheet found in {site_name}")

    hosts_df = xls.parse(hosts_sheet, header=0)

    # Performance sheet for CPU/Mem %
    perf_map = {}
    perf_sheet = sheet_names_lower.get("esx performance")
    if perf_sheet:
        perf_df = xls.parse(perf_sheet, header=0)
        for _, row in perf_df.iterrows():
            h = safe(row.get("Host", ""))
            if h:
                perf_map[h] = row

    # vCenter version from first host row
    vcenter_version = ""
    if not hosts_df.empty:
        vc_str = safe(hosts_df.iloc[0].get("vCenter", ""))
        m = re.search(r'(\d+\.\d+\.\d+)', vc_str)
        if m:
            vcenter_version = m.group(1)

    hosts = []
    for _, row in hosts_df.iterrows():
        hostname = safe(row.get("Host Name", ""))
        if not hostname:
            continue

        # ESXi version from OS field
        esxi_short = ""
        os_str = safe(row.get("OS", ""))
        m = re.search(r'(\d+\.\d+\.\d+)', os_str)
        if m:
            esxi_short = m.group(1)

        perf = perf_map.get(hostname, {})

        hosts.append({
            "hostname": hostname,
            "cluster":  safe(row.get("Cluster", "")) or "Default",
            "model":    safe(row.get("Model", "")),
            "esxi":     esxi_short,
            "vms":      safe(row.get("Guest VM Count", "")) or "0",
            "cpu":      fmt_pct(perf.get("Average CPU %", "")),
            "mem":      fmt_pct(perf.get("Average Memory %", "")),
            "svc":      safe(row.get("Serial No", "")),
        })

    clusters = {}
    for h in hosts:
        clusters.setdefault(h["cluster"], []).append(h)

    return {
        "site_name":       site_name,
        "clusters":        clusters,
        "vcenter_version": vcenter_version,
        "total_hosts":     len(hosts),
        "total_vms":       sum(int(h["vms"]) if str(h["vms"]).isdigit() else 0 for h in hosts),
    }


def parse_file(file_bytes, site_name):
    """Auto-detect RVTools vs LiveOptics and parse accordingly."""
    xls = pd.ExcelFile(io.BytesIO(file_bytes))
    sheets_lower = [s.lower() for s in xls.sheet_names]
    if "vhost" in sheets_lower:
        return parse_rvtools(xls, site_name)
    if "esx hosts" in sheets_lower:
        return parse_liveoptics(xls, site_name)
    raise ValueError(f'"{site_name}" is not a recognised RVTools or LiveOptics export')


# ─── Excalidraw generation ────────────────────────────────────────────────────
def rect(id_, x, y, w, h, bg, stroke, text="", font_size=12, bold=False,
         text_color="#1C2E44", v_align="middle", rounded=8):
    el = {
        "id": id_,
        "type": "rectangle",
        "x": x, "y": y, "width": w, "height": h,
        "angle": 0,
        "strokeColor": stroke,
        "backgroundColor": bg,
        "fillStyle": "solid",
        "strokeWidth": 1,
        "strokeStyle": "solid",
        "roughness": 0,
        "opacity": 100,
        "groupIds": [],
        "roundness": {"type": 3, "value": rounded},
        "seed": hash(id_) & 0xFFFFFF,
        "version": 1,
        "versionNonce": 0,
        "isDeleted": False,
        "boundElements": [],
        "updated": 1,
        "link": None,
        "locked": False,
    }
    elements = [el]
    if text:
        txt_id = uid()
        el["boundElements"].append({"type": "text", "id": txt_id})
        txt = {
            "id": txt_id,
            "type": "text",
            "x": x, "y": y, "width": w, "height": h,
            "angle": 0,
            "strokeColor": text_color,
            "backgroundColor": "transparent",
            "fillStyle": "solid",
            "strokeWidth": 1,
            "strokeStyle": "solid",
            "roughness": 0,
            "opacity": 100,
            "groupIds": [],
            "seed": hash(txt_id) & 0xFFFFFF,
            "version": 1,
            "versionNonce": 0,
            "isDeleted": False,
            "boundElements": [],
            "updated": 1,
            "link": None,
            "locked": False,
            "text": text,
            "fontSize": font_size,
            "fontFamily": 3,  # monospace
            "textAlign": "center",
            "verticalAlign": v_align,
            "containerId": id_,
            "originalText": text,
            "autoResize": True,
            "lineHeight": 1.25,
        }
        if bold:
            txt["fontFamily"] = 1  # normal (bold not native in Excalidraw)
            txt["fontSize"] = font_size + 1
        elements.append(txt)
    return elements


def generate_excalidraw(sites, vcf9_enabled=False):
    """sites: list of dicts from parse_rvtools()"""
    elements = []
    x_cursor = CANVAS_X
    host_h = 140 if vcf9_enabled else HOST_H

    for idx, site in enumerate(sites):
        p = PALETTES[idx % len(PALETTES)]
        clusters = site["clusters"]
        site_name = site["site_name"]
        vc_ver = site["vcenter_version"]
        n_hosts = site["total_hosts"]
        n_vms = site["total_vms"]

        # ── Calculate zone height ──
        zone_inner_y = HEADER_H + PAD
        for cname, chosts in clusters.items():
            rows = (len(chosts) + COLS - 1) // COLS
            zone_inner_y += CLUSTER_H + PAD + rows * (host_h + ROW_GAP)
        zone_h = zone_inner_y + PAD

        # ── Site zone (background) ──
        zone_id = uid()
        y0 = CANVAS_Y
        zone_els = rect(zone_id, x_cursor, y0, ZONE_W, zone_h,
                        bg=p["zone_bg"], stroke=p["zone_stroke"],
                        rounded=12)
        elements.extend(zone_els)

        # ── Site header ──
        hdr_text = f"{site_name}  ·  {n_hosts} hosts  ·  {n_vms} VMs"
        if vc_ver:
            hdr_text += f"\nvCenter {vc_ver}"
        hdr_id = uid()
        hdr_els = rect(hdr_id, x_cursor, y0, ZONE_W, HEADER_H,
                       bg=p["hdr_bg"], stroke=p["hdr_bg"],
                       text=hdr_text, font_size=14, bold=True,
                       text_color=p["hdr_text"], rounded=10)
        elements.extend(hdr_els)

        # ── Clusters ──
        cy = y0 + HEADER_H + PAD
        for cname, chosts in clusters.items():
            # Cluster label bar
            c_id = uid()
            c_els = rect(c_id, x_cursor + PAD, cy, ZONE_W - 2*PAD, CLUSTER_H,
                         bg=p["cluster_bg"], stroke=p["cluster_stroke"],
                         text=cname, font_size=11, bold=True,
                         text_color=p["zone_stroke"], rounded=4)
            elements.extend(c_els)
            cy += CLUSTER_H + PAD

            # Host boxes
            rows = (len(chosts) + COLS - 1) // COLS
            for i, h in enumerate(chosts):
                col_i = i % COLS
                row_i = i // COLS
                hx = x_cursor + PAD + col_i * (HOST_W + COL_GAP)
                hy = cy + row_i * (host_h + ROW_GAP)

                # Build label
                lines = [
                    h["hostname"],
                    h["model"] if h["model"] else "—",
                    f"SVC: {h['svc']}" if h["svc"] else "SVC: —",
                    f"ESXi {h['esxi']}" if h["esxi"] else "ESXi —",
                    f"VMs:{h['vms']}  CPU:{h['cpu']}  Mem:{h['mem']}",
                ]
                if vcf9_enabled and "vcf9" in h:
                    lines.append(h["vcf9"]["label"])
                label = "\n".join(lines)

                stroke = p["host_stroke"]
                if vcf9_enabled and "vcf9" in h and h["vcf9"]["status"] == "incompatible":
                    stroke = "#E57373"

                h_id = uid()
                h_els = rect(h_id, hx, hy, HOST_W, host_h,
                             bg=p["host_bg"], stroke=stroke,
                             text=label, font_size=9,
                             text_color=p["host_text"],
                             v_align="middle", rounded=6)
                elements.extend(h_els)

            cy += rows * (host_h + ROW_GAP) + PAD

        x_cursor += ZONE_W + ZONE_GAP

    # VCF9 legend
    if vcf9_enabled:
        legend_text = "VCF 9 Compatibility\n\u2705 VCF x.x Ready\n\u274C Not VCF9 Ready\n\u26A0\uFE0F VCF9 ? \u2014 model unknown"
        legend_els = rect(uid(), x_cursor, CANVAS_Y, 220, 90,
                          bg="#FFF9E6", stroke="#D4A017",
                          text=legend_text, font_size=9,
                          text_color="#4A4A00", v_align="middle", rounded=8)
        elements.extend(legend_els)

    doc = {
        "type": "excalidraw",
        "version": 2,
        "source": "https://excalidraw.com",
        "elements": elements,
        "appState": {
            "gridSize": None,
            "viewBackgroundColor": "#F4F5F7",
        },
        "files": {},
    }
    return json.dumps(doc, indent=2)


# ─── HTML UI ──────────────────────────────────────────────────────────────────
HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>DrawMyInfra</title>
<style>
  :root {
    --primary:     #2DC4B8;
    --primary-dk:  #22A89E;
    --brand-dark:  #1C2E44;
    --bg:          #EEF4F8;
    --card:        #FFFFFF;
    --border:      #D0DAE6;
    --text:        #2D3748;
    --muted:       #64748B;
  }
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 40px 20px 80px;
  }
  header {
    text-align: center;
    margin-bottom: 40px;
  }
  .logo-img { height: 180px; width: auto; margin-bottom: 4px; }
  .subtitle { color: var(--muted); font-size: 0.95rem; }
  .card {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 32px;
    width: 100%; max-width: 680px;
    box-shadow: 0 2px 16px rgba(0,0,0,.07);
  }
  .drop-zone {
    border: 2.5px dashed var(--border);
    border-radius: 12px;
    padding: 40px 24px;
    text-align: center;
    cursor: pointer;
    transition: border-color .2s, background .2s;
  }
  .drop-zone:hover, .drop-zone.drag-over {
    border-color: var(--primary);
    background: #fff6f2;
  }
  .drop-icon { font-size: 2.5rem; margin-bottom: 10px; }
  .drop-text { font-size: 1rem; color: var(--muted); }
  .drop-text strong { color: var(--primary); cursor: pointer; }
  #file-input { display: none; }

  #file-list { margin-top: 24px; display: flex; flex-direction: column; gap: 10px; }
  .file-row {
    display: flex; align-items: center; gap: 10px;
    background: var(--bg); border: 1px solid var(--border);
    border-radius: 10px; padding: 10px 14px;
  }
  .file-icon { font-size: 1.4rem; }
  .file-name { flex: 1; font-size: 0.9rem; font-weight: 600; color: var(--brand-dark); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .site-input {
    border: 1px solid var(--border); border-radius: 6px;
    padding: 4px 10px; font-size: 0.85rem; width: 130px;
    color: var(--text); outline: none;
    transition: border-color .2s;
  }
  .site-input:focus { border-color: var(--primary); }
  .remove-btn {
    background: none; border: none; cursor: pointer;
    font-size: 1.1rem; color: var(--muted);
    transition: color .15s;
  }
  .remove-btn:hover { color: #e53e3e; }
  #vcf9-option {
    display: flex; align-items: center; gap: 8px;
    margin-top: 18px; font-size: 0.9rem; color: var(--text);
    cursor: pointer; user-select: none;
  }
  #vcf9-option input { accent-color: var(--primary); width: 16px; height: 16px; cursor: pointer; }

  .btn {
    display: block; width: 100%; margin-top: 28px;
    padding: 14px 0; font-size: 1rem; font-weight: 700;
    background: var(--primary); color: #fff;
    border: none; border-radius: 10px; cursor: pointer;
    transition: background .2s, transform .1s;
    letter-spacing: .3px;
  }
  .btn:hover:not(:disabled) { background: var(--primary-dk); transform: translateY(-1px); }
  .btn:disabled { background: #ccc; cursor: not-allowed; transform: none; }

  #status {
    margin-top: 18px; text-align: center;
    font-size: 0.9rem; min-height: 22px;
  }
  .err { color: #e53e3e; }
  .ok  { color: #2d8a4e; font-weight: 600; }
  .spinner {
    display: inline-block; width: 16px; height: 16px;
    border: 2px solid var(--border); border-top-color: var(--primary);
    border-radius: 50%; animation: spin .7s linear infinite;
    vertical-align: middle; margin-right: 6px;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
  footer {
    margin-top: 40px; font-size: 0.8rem; color: var(--muted); text-align: center;
  }
  footer a { color: var(--primary); text-decoration: none; }
</style>
</head>
<body>
<header>
  <img src="/static/logo.png" alt="DrawMyInfra" class="logo-img"/>
  <p class="subtitle">Upload <strong>RVTools</strong> or <strong>LiveOptics</strong> .xlsx exports — get a ready-to-open infrastructure diagram</p>
</header>

<div class="card">
  <div class="drop-zone" id="drop-zone" onclick="document.getElementById('file-input').click()">
    <div class="drop-icon">📂</div>
    <p class="drop-text">Drop your <strong>RVTools</strong> or <strong>LiveOptics</strong> .xlsx files here<br>or <strong>click to browse</strong></p>
  </div>
  <input type="file" id="file-input" accept=".xlsx" multiple/>

  <div id="file-list"></div>
  <label id="vcf9-option">
    <input type="checkbox" id="vcf9-check"/> Check VCF 9 Compatibility (Broadcom Compatibility Guide)
  </label>

  <button class="btn" id="generate-btn" disabled onclick="generate()">
    Generate Excalidraw Diagram
  </button>
  <div id="status"></div>
</div>

<footer>
  Built with ♥ by Florian Casse &nbsp;·&nbsp;
  Open the generated <code>.excalidraw</code> file at
  <a href="https://excalidraw.com" target="_blank">excalidraw.com</a>
</footer>

<script>
const dropZone  = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');
const fileList  = document.getElementById('file-list');
const genBtn    = document.getElementById('generate-btn');
const status    = document.getElementById('status');

let files = []; // {file, name}

function guessName(filename) {
  return filename.replace(/\.xlsx$/i, '').replace(/[_-]/g, ' ').trim();
}

function renderList() {
  fileList.innerHTML = '';
  files.forEach((item, i) => {
    const row = document.createElement('div');
    row.className = 'file-row';

    const icon = document.createElement('span');
    icon.className = 'file-icon';
    icon.textContent = '📄';

    const name = document.createElement('span');
    name.className = 'file-name';
    name.title = item.file.name;
    name.textContent = item.file.name;

    const input = document.createElement('input');
    input.className = 'site-input';
    input.type = 'text';
    input.value = item.name;
    input.placeholder = 'Site name';
    input.addEventListener('input', () => { files[i].name = input.value; });

    const btn = document.createElement('button');
    btn.className = 'remove-btn';
    btn.title = 'Remove';
    btn.textContent = '✕';
    btn.addEventListener('click', () => removeFile(i));

    row.append(icon, name, input, btn);
    fileList.appendChild(row);
  });
  genBtn.disabled = files.length === 0;
}

function addFiles(newFiles) {
  for (const f of newFiles) {
    if (f.name.endsWith('.xlsx') && !files.find(x => x.file.name === f.name)) {
      files.push({ file: f, name: guessName(f.name) });
    }
  }
  renderList();
  status.textContent = '';
}

function setStatus(text, type) {
  status.innerHTML = '';
  if (type === 'loading') {
    const spinner = document.createElement('span');
    spinner.className = 'spinner';
    status.appendChild(spinner);
    status.appendChild(document.createTextNode(' ' + text));
  } else if (type) {
    const span = document.createElement('span');
    span.className = type;
    span.textContent = text;
    status.appendChild(span);
  } else {
    status.textContent = text;
  }
}

function removeFile(i) {
  files.splice(i, 1);
  renderList();
}

fileInput.addEventListener('change', () => addFiles(fileInput.files));

dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('drag-over'); });
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
dropZone.addEventListener('drop', e => {
  e.preventDefault();
  dropZone.classList.remove('drag-over');
  addFiles(e.dataTransfer.files);
});

async function generate() {
  if (!files.length) return;
  genBtn.disabled = true;
  setStatus('Generating diagram…', 'loading');

  const fd = new FormData();
  files.forEach((item, i) => {
    fd.append('files', item.file);
    fd.append('names', item.name || `Site${i+1}`);
  });
  if (document.getElementById('vcf9-check').checked) {
    fd.append('vcf9', '1');
  }

  try {
    const res = await fetch('/generate', { method: 'POST', body: fd });
    if (!res.ok) {
      const err = await res.text();
      setStatus('Error: ' + err, 'err');
      genBtn.disabled = false;
      return;
    }
    const blob = await res.blob();
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href     = url;
    a.download = 'vmware_infrastructure.excalidraw';
    a.click();
    URL.revokeObjectURL(url);
    setStatus('✓ Diagram downloaded! Open it at excalidraw.com', 'ok');
  } catch (e) {
    setStatus('Network error: ' + e.message, 'err');
  } finally {
    genBtn.disabled = false;
  }
}
</script>
</body>
</html>
"""


# ─── Routes ───────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return Response(HTML, mimetype="text/html")


@app.route("/generate", methods=["POST"])
def generate():
    uploaded = request.files.getlist("files")
    names    = request.form.getlist("names")

    if not uploaded:
        return "No files uploaded", 400

    ALLOWED_EXT = {'.xlsx'}
    sites = []
    for i, f in enumerate(uploaded):
        ext = os.path.splitext(f.filename or '')[1].lower()
        if ext not in ALLOWED_EXT:
            return f"Invalid file type: {f.filename}. Only .xlsx files are accepted.", 400
        site_name = names[i] if i < len(names) else f.filename.replace(".xlsx", "")
        try:
            data = parse_file(f.read(), site_name)
            sites.append(data)
        except (ValueError, KeyError, pd.errors.ParserError) as e:
            return f"Error parsing {f.filename}: {str(e)}", 400

    if not sites:
        return "No valid RVTools files found", 400

    # VCF 9 compatibility check
    vcf9_enabled = False
    vcf9_field = request.form.get('vcf9', '').lower()
    if vcf9_field in ('1', 'true', 'on', 'yes'):
        try:
            hcl_data = load_hcl()
            vcf9_lookup = build_vcf9_lookup(hcl_data)
            for site in sites:
                for chosts in site["clusters"].values():
                    for h in chosts:
                        h["vcf9"] = check_vcf9_compat(h["model"], vcf9_lookup)
            vcf9_enabled = True
        except Exception:
            pass  # graceful degradation — continue without VCF9

    try:
        excalidraw_json = generate_excalidraw(sites, vcf9_enabled=vcf9_enabled)
    except (ValueError, KeyError, TypeError) as e:
        return f"Diagram generation error: {str(e)}", 500

    buf = io.BytesIO(excalidraw_json.encode("utf-8"))
    buf.seek(0)
    return send_file(
        buf,
        mimetype="application/json",
        as_attachment=True,
        download_name="vmware_infrastructure.excalidraw",
    )


if __name__ == "__main__":
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    print(f"Starting DrawMyInfra server on http://localhost:{port}")
    app.run(debug=False, host="0.0.0.0", port=port)
