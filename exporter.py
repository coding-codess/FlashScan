"""
exporter.py — export format builders

No UI dependencies. Each function takes the same arguments
and returns a string of file content.

Shares design tokens with the GUI via export_templates/export.css.
"""

from __future__ import annotations

import html as _html
import json
import os
from datetime import datetime
from pathlib import Path


# ── Helpers ──────────────────────────────────────────────────────

_KB = 1_024
_MB = 1_048_576          # 1_024 ** 2
_GB = 1_073_741_824      # 1_024 ** 3

def fmt_size(b: int) -> str:
    if b < _KB: return f"{b} B"
    if b < _MB: return f"{b/_KB:.1f} KB"
    if b < _GB: return f"{b/_MB:.1f} MB"
    return f"{b/_GB:.2f} GB"


def fmt_date(ts: float) -> str:
    if not ts:
        return ""
    return datetime.fromtimestamp(ts).strftime("%d. %m. %Y")


def _esc(s: str) -> str:
    """Escapes HTML special characters for safe insertion into attributes and content."""
    return _html.escape(str(s), quote=True)


# ── Export iterator ───────────────────────────────────────────────

def iter_export(tree: list, folder_states: dict, selected_files: set,
                 active_exts: set | None = None):
    """
    Walks tree and yields only items that should appear in the export.
    Respects folder_states, selected_files and active_exts (extension filter).

    Yields: (lvl, type, name, path, size, mtime, folder_state)
    """
    SEP = os.sep

    skip_prefixes = []
    name_prefixes = []
    for fpath, state in folder_states.items():
        prefix = fpath + SEP
        if state == "skip":
            skip_prefixes.append(prefix)
        elif state == "name":
            name_prefixes.append(prefix)

    def ancestor_state(p: str) -> str | None:
        for sp in skip_prefixes:
            if p.startswith(sp):
                return "skip"
        for np in name_prefixes:
            if p.startswith(np):
                return "name"
        return None

    for item in tree:
        lvl, typ, name, fpath, size, mtime = (
            item["lvl"], item["type"], item["name"],
            item["path"], item["size"], item["mtime"],
        )
        state = folder_states.get(fpath, "full")

        if typ == "folder":
            if state == "skip":
                continue
            block = ancestor_state(fpath)
            if block in ("skip", "name"):
                continue
            yield (lvl, typ, name, fpath, size, mtime, state)

        elif typ == "file":
            if fpath not in selected_files:
                continue
            # Extension filter
            if active_exts is not None:
                ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
                if ext and ext not in active_exts:
                    continue
            block = ancestor_state(fpath)
            if block in ("skip", "name"):
                continue
            parent_state = folder_states.get(str(Path(fpath).parent), "full")
            if parent_state in ("skip", "name"):
                continue
            yield (lvl, typ, name, fpath, size, mtime, "full")


# ── Markdown ──────────────────────────────────────────────────────

def build_md(tree, folder_states, selected_files, meta, active_exts=None) -> str:
    label = meta.get('volume_label', '')
    title = f"{label} ({meta['disk_name']})" if label else meta['disk_name']
    lines = [
        f"# {title} — file list\n",
        f"**Date:** {meta['timestamp']}  ",
        f"**Path:** `{meta['path']}`  ",
        f"**Files:** {meta['file_count']} · **Total:** {meta['total_size']}\n",
        "---\n",
    ]
    for (lvl, typ, name, fpath, size, mtime, state) in iter_export(
            tree, folder_states, selected_files, active_exts):
        indent = "    " * lvl
        if typ == "folder":
            hdr    = "#" * min(lvl + 2, 6)
            suffix = " *(contents omitted)*" if state == "name" else ""
            if lvl <= 1:
                lines.append(f"\n{hdr} {name}{suffix}\n")
            else:
                lines.append(f"{indent}- **{name}/{suffix}**")
        else:
            sz = f" · {fmt_size(size)}" if size else ""
            dt = f" · {fmt_date(mtime)}" if mtime else ""
            lines.append(f"{indent}- {name}{sz}{dt}")
    return "\n".join(lines)


# ── TXT ──────────────────────────────────────────────────────────

def build_txt(tree, folder_states, selected_files, meta, active_exts=None) -> str:
    label = meta.get('volume_label', '')
    title = f"{label} ({meta['disk_name']})" if label else meta['disk_name']
    lines = [
        "=" * 60,
        f"  {title.upper()} — FILE LIST",
        f"  {meta['timestamp']}  |  {meta['path']}",
        f"  {meta['file_count']} files  |  {meta['total_size']}",
        "=" * 60 + "\n",
    ]
    for (lvl, typ, name, fpath, size, mtime, state) in iter_export(
            tree, folder_states, selected_files, active_exts):
        indent = "  " * lvl
        if typ == "folder":
            suffix = "  [name only]" if state == "name" else ""
            lines.append(f"\n{indent}[{name}/{suffix}]")
        else:
            sz = f"  {fmt_size(size):<10}" if size else ""
            dt = f"  {fmt_date(mtime)}" if mtime else ""
            lines.append(f"{indent}  {name}{sz}{dt}")
    return "\n".join(lines)


# ── JSON ─────────────────────────────────────────────────────────

def build_json(tree, folder_states, selected_files, meta, active_exts=None) -> str:
    folders: dict = {}
    current: str | None = None

    for (lvl, typ, name, fpath, size, mtime, state) in iter_export(
            tree, folder_states, selected_files, active_exts):
        if typ == "folder":
            current = fpath
            folders[fpath] = {
                "name":  name,
                "path":  fpath,
                "level": lvl,
                "mode":  state,
                "files": [],
            }
        elif typ == "file" and current:
            folders[current]["files"].append({
                "name":     name,
                "path":     fpath,
                "size":     size,
                "size_fmt": fmt_size(size),
                "date":     fmt_date(mtime),
            })

    return json.dumps(
        {"meta": meta, "folders": list(folders.values())},
        ensure_ascii=False,
        indent=2,
    )


# ── Extension → visual category mapping ───────────────────────────

_EXT_CATEGORIES: dict[str, tuple[str, str]] = {}

def _build_ext_map() -> None:
    groups = [
        ("Images",       "#85b7eb", ['jpg','jpeg','png','gif','bmp','webp','tiff','tif','svg','ico','heic','heif','raw','cr2','nef','arw','dng','psd','ai','eps','avif','jxl']),
        ("Video",        "#AFA9EC", ['mp4','mkv','avi','mov','wmv','flv','webm','m4v','mpg','mpeg','3gp','ts','mts','m2ts','vob','ogv','divx','rmvb','asf','f4v']),
        ("Audio",        "#f09595", ['mp3','wav','flac','aac','ogg','m4a','wma','opus','aiff','ape','mid','midi','amr','ac3','dts','ra','mka','tta','wv']),
        ("Documents",    "#97c459", ['pdf','doc','docx','odt','rtf','txt','md','tex','pages','wpd','wps','epub','mobi','azw','azw3','djvu','xps','oxps','fb2',
                                   'xls','xlsx','ods','csv','tsv','numbers','xlsm','xlsb','xltx','xltm',
                                   'ppt','pptx','odp','key','pps','ppsx','pptm']),
        ("Archives",     "#EF9F27", ['zip','rar','7z','tar','gz','bz2','xz','iso','dmg','pkg','deb','rpm','cab','lzh','lz4','zst','br','tgz','tbz2']),
        ("Code & Data",  "#5DCAA5", ['py','js','ts','jsx','tsx','html','htm','css','scss','sass','php','java','c','cpp','h','cs','go','rs','rb','swift','kt','dart','lua','r','sh','bat','ps1','sql','xml','json','yaml','yml','toml','ini','cfg','conf','env',
                                   'db','sqlite','sqlite3','mdb','accdb','dbf','frm','ibd','mdf','ldf','bak',
                                   'parquet','hdf5','h5','mat','npy','npz','pkl','feather','arrow','nc','fits','zarr',
                                   'ttf','otf','woff','woff2','eot','fon']),
        ("Other",        "#c8c5bc", []),
    ]
    for label, color, exts in groups:
        for e in exts:
            _EXT_CATEGORIES[e] = (label, color)
    _EXT_CATEGORIES["__fallback__"] = ("Other", "#c8c5bc")

_build_ext_map()


def _ext_category(ext: str) -> tuple[str, str]:
    return _EXT_CATEGORIES.get(ext.lower(), _EXT_CATEGORIES["__fallback__"])


# ── HTML ─────────────────────────────────────────────────────────

def build_html(tree, folder_states, selected_files, meta, active_exts=None) -> str:
    css_tokens = _load_export_css()

    items = list(iter_export(tree, folder_states, selected_files, active_exts))

    used_cats: dict[str, str] = {}  # label -> color, preserves insertion order

    def dot(ext: str) -> str:
        label, color = _ext_category(ext)
        used_cats[label] = color
        return f'<span class="dot" style="background:{color}"></span>'

    def render_tree(items: list) -> str:
        parts: list[str] = []
        open_levels: list[int] = []

        # Pre-compute file counts for each folder (including subfolders)
        folder_file_counts: dict[str, int] = {}
        folder_stack: list[tuple[int, str]] = []
        for lvl, typ, name, fpath, size, mtime, state in items:
            if typ == "folder":
                folder_stack = [(l, p) for l, p in folder_stack if l < lvl]
                folder_file_counts[fpath] = 0
                folder_stack.append((lvl, fpath))
            elif typ == "file":
                for _, fp in folder_stack:
                    folder_file_counts[fp] = folder_file_counts.get(fp, 0) + 1

        def close_until(target_lvl: int) -> None:
            while open_levels and open_levels[-1] >= target_lvl:
                parts.append('</div>')      # close .fc
                parts.append('</details>') # close .folder
                open_levels.pop()

        i = 0
        while i < len(items):
            lvl, typ, name, fpath, size, mtime, state = items[i]

            if typ == "folder":
                if lvl == 0:
                    i += 1
                    continue
                close_until(lvl)
                sz_str = fmt_size(size) if size else ""
                fc = folder_file_counts.get(fpath, 0)
                fc_html = f"<b>{fc} files</b>" if fc else ""
                sz_html = _esc(sz_str) if sz_str else ""
                fmeta_parts = [p for p in [sz_html, fc_html] if p]
                fmeta_html = " · ".join(fmeta_parts)
                if state == "name":
                    ename = _esc(name)
                    parts.append(
                        f'<div class="folder">'
                        f'<div class="fh fh-nameonly">'
                        f'<span class="farr">▸</span>'
                        f'<span class="fname fname-muted" title="{ename}/">{ename}/</span>'
                        f'<span class="fmeta">name only{f" · {_esc(sz_str)}" if sz_str else ""}</span>'
                        f'</div>'
                        f'</div>'
                    )
                else:
                    open_attr = " open" if lvl == 0 else ""
                    ename = _esc(name)
                    parts.append(
                        f'<details class="folder"{open_attr}>'
                        f'<summary class="fh">'
                        f'<span class="farr"></span>'
                        f'<span class="fname" title="{ename}/">{ename}/</span>'
                        f'<span class="fmeta">{fmeta_html}</span>'
                        f'</summary>'
                        f'<div class="fc">'
                    )
                    open_levels.append(lvl)

            elif typ == "file":
                ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
                sz_str = fmt_size(size) if size else ""
                dt_str = _esc(fmt_date(mtime)) if mtime else ""
                ename = _esc(name)
                parts.append(
                    f'<div class="fi">'
                    f'{dot(ext)}'
                    f'<span class="fn" title="{ename}">{ename}</span>'
                    f'<span class="fsz">{sz_str}</span>'
                    f'<span class="fdt">{dt_str}</span>'
                    f'</div>'
                )
            i += 1

        close_until(-1)
        return "\n".join(parts)

    tree_html = render_tree(items)

    # Legend — only categories that actually appear, in fixed order
    ORDER = ["Images", "Video", "Audio", "Documents", "Archives", "Code & Data", "Other"]
    legend_items = [
        f'<span class="leg-item"><span class="dot" style="background:{used_cats[k]}"></span>{k}</span>'
        for k in ORDER if k in used_cats
    ]
    legend_html = (
        f'<div class="legend">{"".join(legend_items)}</div>'
        if legend_items else ""
    )

    name_only = meta.get("name_only_count", 0)
    name_only_stat = (
        f'<div class="stat"><div class="sn">{name_only}</div><div class="sl">name only</div></div>'
        if name_only else ""
    )

    label = meta.get('volume_label', '')
    display_name = f"{label}" if label else meta['disk_name']
    display_sub  = meta['disk_name'] if label else ""

    # Escape everything going directly into HTML — file_count/folder_count are int (safe)
    e_display_name = _esc(display_name)
    e_display_sub  = _esc(display_sub)
    e_path         = _esc(meta['path'])
    e_timestamp    = _esc(meta['timestamp'])
    e_total_size   = _esc(meta['total_size'])

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="generator" content="flashscan">
<title>{e_display_name or _esc(meta['disk_name'])} — {meta['file_count']} files</title>
<style>
{css_tokens}
{_EXPORT_CSS}
</style>
</head>
<body>
<div class="page">

  <div class="hdr">
    <div class="hdr-l">
      <div class="disk-name">{e_display_name}</div>
      <div class="disk-path">{e_path}{f' · {e_display_sub}' if display_sub else ''}</div>
      <div class="disk-date">scanned {e_timestamp}</div>
    </div>
    <div class="hdr-r">
      <button id="btn-theme" class="tb-btn tb-btn-theme" onclick="toggleTheme()">\u263e dark</button>
      <div class="watermark">flashscan</div>
    </div>
  </div>

  <div class="stats">
    <div class="stat"><div class="sn">{meta['file_count']}</div><div class="sl">files</div></div>
    <div class="stat"><div class="sn">{e_total_size}</div><div class="sl">total</div></div>
    <div class="stat"><div class="sn">{meta['folder_count']}</div><div class="sl">folders</div></div>
    {name_only_stat}
  </div>

  <div class="tree-toolbar">
    <button onclick="document.querySelectorAll('.tree details').forEach(d=>d.open=true)" class="tb-btn">expand all</button>
    <button onclick="document.querySelectorAll('.tree details').forEach(d=>d.open=false)" class="tb-btn">collapse all</button>
  </div>

  <div class="tree">
{tree_html}
  </div>

  {legend_html}

  <div class="footer">
    <span>flashscan</span>
    <span>{meta['file_count']} files · {e_total_size} · scanned {e_timestamp}</span>
  </div>

</div>
<script>{_THEME_JS}</script>
</body>
</html>"""


def _load_export_css() -> str:
    """Loads tokens.css for inline embedding into the HTML export."""
    try:
        here = Path(__file__).parent
        return (here / "export_templates" / "export.css").read_text(encoding="utf-8")
    except Exception:
        return ""


# CSS specific to HTML export — uses tokens from export.css + custom dark override
_EXPORT_CSS = """
/* ── Export-specific tokens (light) ── */
:root {
  --ex-bg:       #fafaf8;
  --ex-surface:  #f5f3ee;
  --ex-hover:    #f0ede6;
  --ex-border:   #e0ddd6;
  --ex-border2:  #dddad2;
  --ex-text:     #1a1a18;
  --ex-text2:    #444;
  --ex-muted:    #888;
  --ex-subtle:   #bbb;
  --ex-faint:    #ccc;
}
[data-theme="dark"] {
  --ex-bg:       #1e1e1e;
  --ex-surface:  #2a2a2a;
  --ex-hover:    #323232;
  --ex-border:   rgba(255,255,255,.08);
  --ex-border2:  rgba(255,255,255,.06);
  --ex-text:     #d4d0c8;
  --ex-text2:    #b0aca4;
  --ex-muted:    #787470;
  --ex-subtle:   #555;
  --ex-faint:    #444;
}

* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: system-ui, -apple-system, sans-serif; background: var(--ex-bg); color: var(--ex-text); font-size: 13px; transition: background .2s, color .2s; }
.page { max-width: 780px; margin: 0 auto; padding: 36px 24px 64px; }

.hdr { display: flex; justify-content: space-between; align-items: flex-start;
       padding-bottom: 14px; border-bottom: 1px solid var(--ex-border); margin-bottom: 16px; }
.hdr-l { display: flex; flex-direction: column; gap: 3px; }
.hdr-r { display: flex; flex-direction: column; align-items: flex-end; gap: 8px; }
.disk-name { font-size: 22px; font-weight: 700; letter-spacing: -.03em;
             color: var(--ex-text); font-family: 'Courier New', monospace; }
.disk-path { font-size: 11px; color: var(--ex-text2); font-family: 'Courier New', monospace; }
.disk-date { font-size: 11px; color: var(--ex-muted); margin-top: 2px; }
.watermark { font-size: 10px; color: var(--ex-subtle); letter-spacing: .08em; text-transform: uppercase; }

.stats { display: flex; gap: 8px; margin-bottom: 20px; }
.stat { flex: 1; padding: 11px 14px; border: 1px solid var(--ex-border); border-radius: 4px; }
.sn { font-size: 19px; font-weight: 700; letter-spacing: -.02em; font-family: 'Courier New', monospace; }
.sl { font-size: 11px; color: var(--ex-muted); margin-top: 3px; }

.folder { margin-bottom: 2px; }
.fh { display: flex; align-items: baseline; padding: 5px 4px; gap: 5px;
      list-style: none; cursor: pointer; user-select: none; border-radius: 3px; }
.fh:hover { background: var(--ex-hover); }
.fh::-webkit-details-marker { display: none; }
.fh-nameonly { cursor: default; }
.fh-nameonly .fname { color: var(--ex-subtle); font-weight: 400; }
.fh-nameonly .fmeta { font-style: italic; }
.farr { font-size: 13px; color: var(--ex-subtle); flex-shrink: 0; width: 14px;
        display: inline-block; transition: transform .15s; }
.farr::before { content: '▸'; }
details[open] > .fh > .farr { transform: rotate(90deg); }
details:not([open]) > .fh > .farr { transform: rotate(0deg); }
.fname { font-size: 13px; font-weight: 600; color: var(--ex-text);
         font-family: 'Courier New', monospace; flex: 1;
         min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.fname-muted { color: var(--ex-subtle); font-weight: 400; }
.fmeta { font-size: 11px; color: var(--ex-subtle); flex-shrink: 0; white-space: nowrap; }
.fc { margin-left: 9px; padding-left: 12px; border-left: 1px solid var(--ex-border2); }

.fc > .fi:nth-child(even) { background: var(--ex-surface); }
.fi { display: flex; align-items: center; padding: 3px 4px; gap: 0; border-radius: 3px; }
.fi:hover { background: var(--ex-hover); }
.dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; margin-right: 8px; }
.fn { font-size: 12px; color: var(--ex-text2); font-family: 'Courier New', monospace;
      flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.fsz { font-size: 11px; color: var(--ex-subtle); margin-left: 10px; flex-shrink: 0; white-space: nowrap; }
.fdt { font-size: 11px; font-weight: 700; color: var(--ex-text2); margin-left: 8px; flex-shrink: 0; white-space: nowrap; }

.legend { display: flex; gap: 16px; flex-wrap: wrap; margin-top: 20px;
          padding-top: 14px; border-top: 1px solid var(--ex-border); }
.leg-item { display: flex; align-items: center; gap: 6px; font-size: 11px; color: var(--ex-muted); }

.tree-toolbar { display: flex; gap: 8px; margin-bottom: 10px; }
.tb-btn { font-size: 11px; background: none; border: 1px solid var(--ex-border2);
          border-radius: 3px; padding: 3px 9px; cursor: pointer; font-family: inherit; color: var(--ex-muted); }
.tb-btn:hover { background: var(--ex-hover); color: var(--ex-text2); border-color: var(--ex-subtle); }
.tb-btn-theme { font-size: 10px; padding: 2px 8px; }

.footer { margin-top: 24px; padding-top: 12px; border-top: 1px solid var(--ex-border);
          display: flex; justify-content: space-between; font-size: 10px;
          color: var(--ex-faint); letter-spacing: .04em; text-transform: uppercase; }
"""

_THEME_JS = """
  function applyTheme(theme) {
    if (theme === 'dark') {
      document.documentElement.dataset.theme = 'dark';
      document.getElementById('btn-theme').textContent = '\u2600 light';
    } else {
      delete document.documentElement.dataset.theme;
      document.getElementById('btn-theme').textContent = '\u263e dark';
    }
    try { localStorage.setItem('flashscan-theme', theme); } catch(e) {}
  }
  function toggleTheme() {
    applyTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark');
  }
  try {
    var saved = localStorage.getItem('flashscan-theme');
    if (saved) applyTheme(saved);
  } catch(e) {}
"""
