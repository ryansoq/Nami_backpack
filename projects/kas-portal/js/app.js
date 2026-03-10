/**
 * 🌊 Kas Portal - UI Logic
 */

const $ = (sel) => document.querySelector(sel);

let worker = null;
let mining = false;

// UI Elements
const btnStart = $('#btn-start');
const btnStop = $('#btn-stop');
const inputWallet = $('#wallet-address');
const inputWsUrl = $('#ws-url');
const statusEl = $('#status');
const hashrateEl = $('#hashrate');
const hashesEl = $('#total-hashes');
const blocksEl = $('#blocks-found');
const elapsedEl = $('#elapsed');
const logEl = $('#log');

// Event listeners
btnStart.addEventListener('click', startMining);
btnStop.addEventListener('click', stopMining);

function startMining() {
  if (mining) return;

  const walletAddress = inputWallet.value.trim();
  // Auto-detect wRPC endpoint: use /ws proxy if accessed via HTTP
  let wsUrl = inputWsUrl.value.trim();
  if (!wsUrl) {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    wsUrl = `${proto}//${location.host}/ws`;
  }

  if (!walletAddress) {
    addLog('❌ Please enter a wallet address');
    return;
  }

  mining = true;
  btnStart.disabled = true;
  btnStop.disabled = false;
  btnStart.classList.add('hidden');
  btnStop.classList.remove('hidden');

  // Create worker (ES module for ESM imports)
  worker = new Worker('js/miner.js', { type: 'module' });

  worker.onmessage = (e) => {
    const { type, data } = e.data;

    switch (type) {
      case 'status':
        updateStatus(data);
        break;
      case 'stats':
        updateStats(data);
        break;
      case 'log':
        addLog(data);
        break;
      case 'found':
        onBlockFound(data);
        break;
      case 'accepted':
        onBlockAccepted();
        break;
    }
  };

  worker.onerror = (e) => {
    addLog(`❌ Worker error: ${e.message}`);
    stopMining();
  };

  worker.postMessage({
    type: 'start',
    data: { wsUrl, walletAddress }
  });

  addLog('🌊 Starting miner...');
}

function stopMining() {
  if (!mining) return;

  mining = false;
  btnStart.disabled = false;
  btnStop.disabled = true;
  btnStart.classList.remove('hidden');
  btnStop.classList.add('hidden');

  if (worker) {
    worker.postMessage({ type: 'stop' });
    setTimeout(() => {
      worker.terminate();
      worker = null;
    }, 1000);
  }

  updateStatus('stopped');
  addLog('⏹ Miner stopped');
}

function updateStatus(status) {
  const labels = {
    connecting: '🔗 Connecting...',
    connected: '✅ Connected',
    reconnecting: '🔄 Reconnecting...',
    mining: '⛏️ Mining',
    stopped: '⏹ Stopped',
    error: '❌ Error'
  };
  statusEl.textContent = labels[status] || status;
  statusEl.className = `status-${status}`;
}

function updateStats(data) {
  hashrateEl.textContent = `${data.hashrate} H/s`;
  hashesEl.textContent = data.hashes.toLocaleString();
  blocksEl.textContent = data.blocks;

  const mins = Math.floor(data.elapsed / 60);
  const secs = Math.floor(data.elapsed % 60);
  elapsedEl.textContent = `${mins}m ${secs}s`;

  // Animate hashrate
  hashrateEl.classList.add('pulse');
  setTimeout(() => hashrateEl.classList.remove('pulse'), 300);
}

function onBlockFound(data) {
  addLog(`💎 FOUND! nonce=${data.nonce}`);

  // Flash effect
  const container = $('.container');
  container.classList.add('block-found');
  setTimeout(() => container.classList.remove('block-found'), 2000);

  // Update counter
  const current = parseInt(blocksEl.textContent) || 0;
  blocksEl.textContent = current + 1;
}

function onBlockAccepted() {
  addLog('🎉 Block ACCEPTED by network!');

  // Extra celebration
  const container = $('.container');
  container.classList.add('block-accepted');
  setTimeout(() => container.classList.remove('block-accepted'), 3000);
}

function addLog(msg) {
  const time = new Date().toLocaleTimeString();
  const line = document.createElement('div');
  line.className = 'log-line';
  line.textContent = `[${time}] ${msg}`;
  logEl.appendChild(line);
  logEl.scrollTop = logEl.scrollHeight;

  // Keep only last 100 lines
  while (logEl.children.length > 100) {
    logEl.removeChild(logEl.firstChild);
  }
}

// Init
updateStatus('stopped');
addLog('🌊 Kas Portal ready. Press ⛏️ to start mining.');
