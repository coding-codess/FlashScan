/**
 * export.js — communication with the Python backend for export
 *
 * Calls window.pywebview.api.export() and displays the result.
 * Also updates the summary box on the export screen.
 */

const Export = {
  init() {
    document.getElementById('btn-export')?.addEventListener('click', () => this.doExport());
    document.getElementById('btn-browse-out')?.addEventListener('click', () => this.browseOutput());
  },

  /** Updates the summary box when switching to screen 2 */
  updateSummary() {
    const { count, size, nameOnly } = State.exportStats();
    const fmts   = this._selectedFormats();
    const outPath = document.getElementById('out-input')?.value || '';
    const diskName = this._diskName();

    let parts = [`<strong>${count} files</strong>`];
    if (size) parts.push(fmtSize(size));
    if (nameOnly) parts.push(`${nameOnly} folders name only`);
    if (fmts.length) parts.push(`format: <strong>${fmts.join(', ')}</strong>`);
    else             parts.push('<span class="export-warn">⚠ no format selected</span>');

    const ts   = new Date().toISOString().slice(0,10).replace(/-/g, '-');
    const fnamesHtml = fmts.length
      ? fmts.map(f => `<strong style="color:var(--text2)">LIST_${diskName}_${ts}.${f.toLowerCase()}</strong>`).join('<br>')
      : '—';

    const el = document.getElementById('export-summary');
    if (el) {
      el.innerHTML = parts.join(' · ')
        + `<br><span style="color:var(--text3)">output:<br>${fnamesHtml}</span>`;
    }
  },

  _diskName() {
    if (State.volumeLabel) return State.volumeLabel;
    const path = document.getElementById('path-input')?.value || '';
    const parts = path.replace(/\\/g, '/').split('/').filter(Boolean);
    return parts[parts.length - 1] || 'DISK';
  },

  _selectedFormats() {
    return [...document.querySelectorAll('.fmt-cell.selected')]
      .map(el => el.dataset.fmt)
      .filter(Boolean);
  },

  async browseOutput() {
    try {
      const dir = await window.pywebview.api.browse_directory();
      if (dir) {
        const el = document.getElementById('out-input');
        if (el) el.value = dir;
        window.pywebview?.api?.save_settings({ lastOutput: dir });
      }
    } catch (e) {
      console.error('browseOutput error', e);
    }
  },

  async doExport() {
    const fmts   = this._selectedFormats();
    const outDir = document.getElementById('out-input')?.value?.trim();

    if (!fmts.length) {
      this._showResult('Select at least one format.', 'error');
      return;
    }
    if (!outDir) {
      this._showResult('Enter an output folder.', 'error');
      document.getElementById('out-input')?.focus();
      return;
    }

    const btn  = document.getElementById('btn-export');
    const wrap = document.getElementById('export-progress-wrap');
    const bar  = document.getElementById('export-progress-bar');
    const txt  = document.getElementById('export-status-text');
    try {
      if (btn)  { btn.disabled = true; btn.textContent = 'Exporting…'; }
      if (wrap) wrap.style.display = 'flex';
      if (bar)  bar.classList.add('animated');
      if (txt)  txt.textContent = 'Exporting…';
      const exportResult = document.getElementById('export-result');
      if (exportResult) exportResult.style.display = 'none';

      // Build payload for Python
      const payload = {
        formats:        fmts,
        output_dir:     outDir,
        path:           document.getElementById('path-input')?.value?.trim() || '',
        volume_label:   State.volumeLabel || '',
        tree:           State.treeData,
        folder_states:  State.folderStates,
        selected_files: [...State.selectedFiles],
        active_exts:    State.activeExts ? [...State.activeExts] : null,
      };

      const result = await window.pywebview.api.export(payload);

      if (result.success) {
        const saved = result.saved || [];
        this._showResultFiles(saved, result.errors || []);
      } else {
        this._showResult('Error: ' + (result.error || 'unknown error'), 'error');
      }
    } catch (e) {
      this._showResult('Export error: ' + e.message, 'error');
    } finally {
      if (btn)  { btn.disabled = false; btn.innerHTML = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg> export'; }
      if (bar)  bar.classList.remove('animated');
      if (wrap) wrap.style.display = 'none';
    }
  },

  _showResult(msg, type) {
    const el = document.getElementById('export-result');
    if (!el) return;
    el.style.display = '';
    el.className     = `export-result ${type}`;
    el.textContent   = msg;
  },

  _showResultFiles(saved, errors) {
    const el = document.getElementById('export-result');
    if (!el) return;
    el.style.display = '';
    el.className     = 'export-result success';

    const errHtml = errors.length
      ? `<span class="export-errors">${errors.join('<br>')}</span>`
      : '';

    el.innerHTML = `<span class="export-saved-label">Saved:</span>${
      saved.map((p, i) => {
        const name = p.replace(/.*[\/\\]/, '');
        return `<span class="export-file-row">
          <a class="export-file-link" data-path="${p}" data-idx="${i}" title="Open file">${name}</a>
          <span class="export-file-actions">
            <a class="export-file-open" data-path="${p}" data-idx="${i}" title="Open file"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/></svg></a>
            <a class="export-file-reveal" data-path="${p}" data-idx="${i}" title="Show in Finder / Explorer"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg></a>
          </span>
        </span>`;
      }).join('')
    }${errHtml}<div class="export-new-scan-row"><button class="btn btn-secondary" id="btn-new-scan">← new scan</button></div>`;

    el.querySelectorAll('.export-file-link, .export-file-open').forEach(a => {
      a.addEventListener('click', () => {
        window.pywebview.api.open_path(a.dataset.path);
      });
    });
    el.querySelectorAll('.export-file-reveal').forEach(a => {
      a.addEventListener('click', () => {
        window.pywebview.api.reveal_in_explorer(a.dataset.path);
      });
    });

    document.getElementById('btn-new-scan')?.addEventListener('click', () => {
      Nav.reset();
    });
  },
};

/** fmtSize available globally (defined in tree.js, loaded earlier) */
