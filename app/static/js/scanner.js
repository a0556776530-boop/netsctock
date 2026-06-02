/**
 * InventoryScanner — reusable inline scanner widget.
 * Requires html5-qrcode and Bootstrap 5 to be loaded on the page.
 *
 * Usage:
 *   const scanner = new InventoryScanner({
 *     triggerBtn:  document.getElementById('scanSerial'),
 *     targetInput: document.getElementById('serialInput'),
 *     lookupUrl:   '/scan/api/lookup',
 *     onResult:    (data) => {}   // optional
 *   });
 */
class InventoryScanner {
  constructor({ triggerBtn, targetInput, lookupUrl, onResult }) {
    this.targetInput = targetInput;
    this.lookupUrl   = lookupUrl;
    this.onResult    = onResult || (() => {});
    this.scanner     = null;
    this.active      = false;
    this.cooldown    = false;

    this._buildModal();

    if (triggerBtn) {
      triggerBtn.addEventListener('click', e => {
        e.preventDefault();
        this.open();
      });
    }
  }

  _buildModal() {
    const id = 'nscanModal_' + Math.random().toString(36).slice(2);
    this.previewId = 'nscanPreview_' + Math.random().toString(36).slice(2);

    const tpl = document.createElement('div');
    tpl.innerHTML = `
      <div class="modal fade" id="${id}" tabindex="-1" data-bs-backdrop="static">
        <div class="modal-dialog modal-dialog-centered">
          <div class="modal-content">
            <div class="modal-header py-2">
              <h6 class="modal-title mb-0"><i class="bi bi-upc-scan me-2"></i>Scan Serial Number</h6>
              <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
            </div>
            <div class="modal-body p-0">
              <div class="bg-dark" style="min-height:200px; position:relative;">
                <div id="${this.previewId}"></div>
                <div class="position-absolute top-0 start-0 w-100 h-100 d-flex align-items-center justify-content-center" style="pointer-events:none;">
                  <div class="modal-scan-frame"><div class="modal-scan-line"></div></div>
                </div>
              </div>
              <div class="p-3">
                <div id="${id}_status" class="small text-muted text-center mb-2">Starting camera…</div>
                <div id="${id}_result" class="d-none alert py-2 mb-0 small"></div>
              </div>
            </div>
            <div class="modal-footer py-2">
              <button type="button" class="btn btn-secondary btn-sm" data-bs-dismiss="modal">Cancel</button>
            </div>
          </div>
        </div>
      </div>`;
    document.body.appendChild(tpl.firstElementChild);

    this.modalEl  = document.getElementById(id);
    this.statusEl = document.getElementById(id + '_status');
    this.resultEl = document.getElementById(id + '_result');
    this.bsModal  = new bootstrap.Modal(this.modalEl);

    this.modalEl.addEventListener('hidden.bs.modal', () => this._stop());
  }

  open() {
    this.bsModal.show();
    setTimeout(() => this._start(), 400);
  }

  async _start() {
    this.scanner = new Html5Qrcode(this.previewId);
    const config = {
      fps: 12,
      qrbox: { width: 260, height: 100 },
      formatsToSupport: [
        Html5QrcodeSupportedFormats.CODE_128,
        Html5QrcodeSupportedFormats.CODE_39,
        Html5QrcodeSupportedFormats.QR_CODE,
        Html5QrcodeSupportedFormats.DATA_MATRIX,
      ],
    };
    try {
      await this.scanner.start({ facingMode: 'environment' }, config,
        text => this._onScan(text), () => {});
      this.active = true;
      this.statusEl.textContent = 'Hold barcode in the frame…';
    } catch (_) {
      this.statusEl.textContent = 'Camera unavailable — type the serial number manually.';
      this.scanner = null;
    }
  }

  async _stop() {
    this.active = false;
    if (this.scanner) {
      try { await this.scanner.stop(); } catch (_) {}
      this.scanner = null;
    }
    const preview = document.getElementById(this.previewId);
    if (preview) preview.innerHTML = '';
    this.resultEl.className = 'd-none alert py-2 mb-0 small';
    this.resultEl.textContent = '';
    this.statusEl.textContent = 'Starting camera…';
  }

  async _onScan(text) {
    if (!this.active || this.cooldown) return;
    this.cooldown = true;
    setTimeout(() => { this.cooldown = false; }, 2000);

    const value = text.trim().toUpperCase();
    this.statusEl.textContent = 'Scanned: ' + value;
    if (this.targetInput) this.targetInput.value = value;

    if (this.lookupUrl) {
      try {
        const res = await fetch(this.lookupUrl + '?q=' + encodeURIComponent(value));
        if (!res.ok) throw new Error('Server error ' + res.status);
        const data = await res.json();
        this._showResult(data, value);
        this.onResult(data);
        setTimeout(() => this.bsModal.hide(), data.found ? 1800 : 2500);
      } catch (_) {
        this._showResult(null, value);
        setTimeout(() => this.bsModal.hide(), 800);
      }
    } else {
      setTimeout(() => this.bsModal.hide(), 600);
    }
  }

  _esc(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  _showResult(data, value) {
    const el  = this.resultEl;
    const val = this._esc(value);
    el.classList.remove('d-none', 'alert-success', 'alert-warning', 'alert-info');
    if (!data) {
      el.classList.add('alert-info');
      el.textContent = 'Scanned: ' + value;
    } else if (data.found) {
      el.classList.add('alert-success');
      el.innerHTML = '<i class="bi bi-check-circle me-1"></i><strong>' + val + '</strong> found — ' + this._esc(data.asset.status_label);
    } else {
      el.classList.add('alert-warning');
      el.innerHTML = '<i class="bi bi-question-circle me-1"></i><strong>' + val + '</strong> not yet registered.';
    }
  }
}
