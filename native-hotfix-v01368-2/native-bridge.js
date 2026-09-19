(function () {
  'use strict';
  if (!window.chrome || !window.chrome.webview) return;

  let sequence = 0;
  const pending = new Map();
  const request = (action, payload) => new Promise((resolve, reject) => {
    const id = `hca-${Date.now()}-${++sequence}`;
    pending.set(id, { resolve, reject });
    window.chrome.webview.postMessage({ id, action, payload: payload || {} });
  });

  window.chrome.webview.addEventListener('message', event => {
    const message = event.data || {};
    if (message.type !== 'hca-native-result' || !pending.has(message.id)) return;
    const item = pending.get(message.id);
    pending.delete(message.id);
    if (message.ok) item.resolve(message.result);
    else item.reject(new Error(message.error || 'HCA-Systemfehler'));
  });

  const bytesToBase64 = bytes => {
    let binary = '';
    const chunk = 8192;
    for (let offset = 0; offset < bytes.length; offset += chunk) {
      binary += String.fromCharCode.apply(null, bytes.subarray(offset, Math.min(bytes.length, offset + chunk)));
    }
    return btoa(binary);
  };

  const base64ToBytes = value => {
    if (!value) return new Uint8Array(0);
    const binary = atob(value);
    const bytes = new Uint8Array(binary.length);
    for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
    return bytes;
  };

  class HcaSerialPort {
    constructor(name) {
      this.name = name;
      this.readable = null;
      this.writable = null;
    }

    async open(options) {
      await request('serial.open', Object.assign({ port: this.name }, options || {}));
      const port = this.name;
      this.readable = {
        getReader() {
          let released = false;
          return {
            async read() {
              if (released) return { value: undefined, done: true };
              const result = await request('serial.read', { port });
              return { value: base64ToBytes(result && result.data), done: !!(result && result.done) };
            },
            async cancel() { released = true; },
            releaseLock() { released = true; }
          };
        }
      };
      this.writable = {
        getWriter() {
          let released = false;
          return {
            async write(value) {
              if (released) throw new Error('Der serielle Schreiber wurde bereits freigegeben.');
              const bytes = value instanceof Uint8Array ? value : new Uint8Array(value);
              return request('serial.write', { port, data: bytesToBase64(bytes) });
            },
            releaseLock() { released = true; }
          };
        }
      };
    }

    async close() {
      await request('serial.close', { port: this.name });
      this.readable = null;
      this.writable = null;
    }
  }

  const hcaSerial = {
    async requestPort() {
      const selected = await request('serial.select', {});
      return new HcaSerialPort(selected.port);
    },
    async getPorts() { return []; },
    addEventListener() {},
    removeEventListener() {}
  };

  window.hcaNative = Object.freeze({
    async printPdf(bytes, printer) {
      const value = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes || []);
      return request('document.print', { data: bytesToBase64(value), printer: String(printer || '') });
    }
  });

  try {
    Object.defineProperty(navigator, 'serial', { configurable: false, enumerable: true, value: hcaSerial });
  } catch (_) {
    try {
      navigator.serial.requestPort = hcaSerial.requestPort;
      navigator.serial.getPorts = hcaSerial.getPorts;
    } catch (_) {
      window.hcaSerial = hcaSerial;
    }
  }
})();
