/**
 * 🌊 Kaspa wRPC WebSocket Client
 * 
 * Kaspa wRPC uses JSON-RPC over WebSocket.
 * Methods: getBlockTemplate, submitBlock
 */

class KaspaWRPC {
  constructor(url) {
    this.url = url;
    this.ws = null;
    this.requestId = 0;
    this.pending = new Map(); // id -> {resolve, reject}
    this.onConnect = null;
    this.onDisconnect = null;
    this.onError = null;
    this.reconnectTimer = null;
    this.connected = false;
  }

  connect() {
    return new Promise((resolve, reject) => {
      try {
        this.ws = new WebSocket(this.url);
      } catch (e) {
        reject(e);
        return;
      }

      this.ws.onopen = () => {
        this.connected = true;
        if (this.onConnect) this.onConnect();
        resolve();
      };

      this.ws.onclose = () => {
        this.connected = false;
        if (this.onDisconnect) this.onDisconnect();
        // Auto-reconnect after 3s
        this.reconnectTimer = setTimeout(() => this.connect().catch(() => {}), 3000);
      };

      this.ws.onerror = (e) => {
        this.connected = false;
        if (this.onError) this.onError(e);
        reject(e);
      };

      this.ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          this._handleMessage(data);
        } catch (e) {
          console.error('wRPC parse error:', e);
        }
      };
    });
  }

  disconnect() {
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    if (this.ws) {
      this.ws.onclose = null; // Prevent auto-reconnect
      this.ws.close();
      this.ws = null;
    }
    this.connected = false;
  }

  _handleMessage(data) {
    // wRPC response format: { id, method, params OR result, error }
    // Kaspa wRPC wraps responses in method-specific keys
    const id = data.id;
    if (id !== undefined && this.pending.has(id)) {
      const { resolve, reject } = this.pending.get(id);
      this.pending.delete(id);
      if (data.error) {
        reject(new Error(data.error.message || JSON.stringify(data.error)));
      } else {
        resolve(data.params || data.result || data);
      }
    }
  }

  _call(method, params = {}) {
    return new Promise((resolve, reject) => {
      if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
        reject(new Error('Not connected'));
        return;
      }

      const id = this.requestId++;
      this.pending.set(id, { resolve, reject });

      // Kaspa wRPC format
      const msg = { id, method, params };
      this.ws.send(JSON.stringify(msg));

      // Timeout
      setTimeout(() => {
        if (this.pending.has(id)) {
          this.pending.delete(id);
          reject(new Error('Request timeout'));
        }
      }, 10000);
    });
  }

  async getBlockTemplate(payAddress, extraData = '') {
    return this._call('getBlockTemplate', { payAddress, extraData });
  }

  async submitBlock(block) {
    return this._call('submitBlock', { block, allowNonDAABlocks: true });
  }

  async getInfo() {
    return this._call('getInfo', {});
  }
}

if (typeof self !== 'undefined') {
  self.KaspaWRPC = KaspaWRPC;
}
