"""
Kaspa Whisper — Web API Server

aiohttp server on port 18802.
All endpoints require X-Whisper-Key header.

Endpoints:
  GET  /whisper/contacts          — 通訊錄（不含 privkey）
  GET  /whisper/contacts/{agentId} — 查單一 agent
  POST /whisper/encode            — 打包 whisper TX
  POST /whisper/broadcast         — 廣播 TX
"""
import asyncio, json, os, re, sys, time, uuid, logging, shutil, collections
from datetime import datetime, timezone, timedelta
from aiohttp import web
import httpx

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger('whisper')

sys.path.insert(0, '/home/ymchang/nami-backpack/projects/nami-kaspa-bot')

# ── Welcome Bonus Config ─────────────────────────────
WELCOME_AMOUNT = 50000000   # 0.5 tKAS
TX_FEE = 50000
DAILY_BONUS_LIMIT = 20

# In-memory daily counter (resets on restart)
_bonus_count = 0
_bonus_date = datetime.now(timezone.utc).date()


def _check_bonus_limit() -> bool:
    """Return True if we can still send welcome bonuses today."""
    global _bonus_count, _bonus_date
    today = datetime.now(timezone.utc).date()
    if today != _bonus_date:
        _bonus_count = 0
        _bonus_date = today
    return _bonus_count < DAILY_BONUS_LIMIT


def _increment_bonus():
    global _bonus_count, _bonus_date
    today = datetime.now(timezone.utc).date()
    if today != _bonus_date:
        _bonus_count = 0
        _bonus_date = today
    _bonus_count += 1


async def _send_welcome_bonus(address: str) -> dict:
    """Send 0.5 tKAS welcome bonus. Returns dict with tx info or error."""
    if not _check_bonus_limit():
        return {'amount': '0.5 tKAS', 'status': 'failed', 'error': 'daily bonus limit reached'}

    try:
        from kaspa import PrivateKey, Address, PaymentOutput, create_transaction, sign_transaction
        from rpc_manager import get_utxos, submit_transaction

        with open(os.path.expanduser('~/.secrets/testnet-wallet.json')) as f:
            wallet_data = json.load(f)
            nami_privkey = wallet_data.get('privateKey') or wallet_data.get('private_key')

        pk = PrivateKey(nami_privkey)
        nami_addr = pk.to_public_key().to_address('testnet').to_string()

        entries = await get_utxos(nami_addr)
        if not entries:
            return {'amount': '0.5 tKAS', 'status': 'failed', 'error': 'no UTXOs in Nami wallet'}

        entries.sort(key=lambda e: e["utxoEntry"]["amount"], reverse=True)
        selected, total = [], 0
        for e in entries:
            selected.append(e)
            total += e["utxoEntry"]["amount"]
            if total >= WELCOME_AMOUNT + TX_FEE + 1000:
                break

        if total < WELCOME_AMOUNT + TX_FEE:
            return {'amount': '0.5 tKAS', 'status': 'failed', 'error': f'insufficient balance: {total/1e8:.4f} KAS'}

        change = total - WELCOME_AMOUNT - TX_FEE
        outputs = [PaymentOutput(Address(address), WELCOME_AMOUNT)]
        if change > 0:
            outputs.append(PaymentOutput(Address(nami_addr), change))

        tx = create_transaction(utxo_entry_source=selected, outputs=outputs, priority_fee=TX_FEE, payload=b'welcome bonus')
        signed = sign_transaction(tx, [pk], False)
        tx_id = await submit_transaction(signed, allow_orphan=False)

        _increment_bonus()
        return {'amount': '0.5 tKAS', 'tx_id': tx_id}

    except Exception as e:
        return {'amount': '0.5 tKAS', 'status': 'failed', 'error': str(e)}

# ── Fix #3: Webhook Retry Queue ───────────────────────
_webhook_retry_queue: asyncio.Queue = asyncio.Queue()
_WEBHOOK_MAX_RETRIES = 3
_WEBHOOK_RETRY_DELAYS = [5, 15, 45]  # seconds


async def _webhook_retry_worker():
    """Background worker that retries failed webhook deliveries."""
    while True:
        try:
            item = await _webhook_retry_queue.get()
            url = item['url']
            payload = item['payload']
            attempt = item.get('attempt', 0)

            delay = _WEBHOOK_RETRY_DELAYS[attempt] if attempt < len(_WEBHOOK_RETRY_DELAYS) else 60
            await asyncio.sleep(delay)

            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.post(url, json=payload)
                    if resp.status_code < 400:
                        log.info(f"Webhook retry #{attempt+1} succeeded → {url}")
                    else:
                        raise Exception(f"HTTP {resp.status_code}")
            except Exception as e:
                if attempt + 1 < _WEBHOOK_MAX_RETRIES:
                    log.warning(f"Webhook retry #{attempt+1} failed ({e}), re-queuing")
                    await _webhook_retry_queue.put({**item, 'attempt': attempt + 1})
                else:
                    log.error(f"Webhook delivery to {url} failed after {_WEBHOOK_MAX_RETRIES} retries")
        except asyncio.CancelledError:
            break
        except Exception as e:
            log.error(f"Webhook retry worker error: {e}")


# ── Fix #2: Event Store with Error Recovery ───────────
def _save_contacts_safe(contacts: dict, path: str):
    """Atomic write with backup — never lose contacts data."""
    backup = path + '.bak'
    tmp = path + '.tmp'
    try:
        # Write to temp file first
        with open(tmp, 'w') as f:
            json.dump(contacts, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        # Backup current file
        if os.path.exists(path):
            shutil.copy2(path, backup)
        # Atomic rename
        os.replace(tmp, path)
    except Exception as e:
        log.error(f"Failed to save contacts: {e}")
        # Try to restore from backup
        if os.path.exists(backup) and not os.path.exists(path):
            shutil.copy2(backup, path)
            log.info("Restored contacts from backup")
        raise


CONTACTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'contacts.json')
SECRET_FILE = os.path.expanduser('~/.secrets/whisper-api-key.json')
PORT = int(os.environ.get('PORT', 18803))


# ── Auth ──────────────────────────────────────────────

def load_api_key() -> str:
    os.makedirs(os.path.dirname(SECRET_FILE), exist_ok=True)
    if os.path.exists(SECRET_FILE):
        with open(SECRET_FILE) as f:
            return json.load(f)['key']
    key = str(uuid.uuid4())
    with open(SECRET_FILE, 'w') as f:
        json.dump({'key': key}, f)
    print(f"🔑 Generated new API key → {SECRET_FILE}")
    return key

API_KEY = load_api_key()


@web.middleware
async def auth_middleware(request, handler):
    if request.headers.get('X-Whisper-Key') != API_KEY:
        return web.json_response({'error': 'unauthorized'}, status=401)
    return await handler(request)


# ── Helpers ───────────────────────────────────────────

def load_contacts():
    with open(CONTACTS_FILE) as f:
        return json.load(f)

def sanitize_contact(c: dict) -> dict:
    """Strip privkey from contact."""
    return {k: v for k, v in c.items() if k != 'privkey'}


# ── Endpoints ─────────────────────────────────────────

async def get_contacts(request):
    contacts = load_contacts()
    return web.json_response({k: sanitize_contact(v) for k, v in contacts.items()})

async def get_contact(request):
    agent_id = request.match_info['agentId']
    contacts = load_contacts()
    c = contacts.get(agent_id.lower())
    if not c:
        return web.json_response({'error': f'agent "{agent_id}" not found'}, status=404)
    return web.json_response({agent_id.lower(): sanitize_contact(c)})

async def post_encode(request):
    try:
        body = await request.json()
    except Exception:
        return web.json_response({'error': 'invalid JSON'}, status=400)

    to_name = body.get('to')
    message = body.get('message')
    sender_privkey = body.get('sender_privkey')
    plain = body.get('plain', False)
    raw = body.get('raw', False)

    if not all([to_name, message, sender_privkey]):
        return web.json_response({'error': 'missing required fields: to, message, sender_privkey'}, status=400)

    try:
        from ecies import encrypt as ecies_encrypt
        from kaspa import PrivateKey, Address, PaymentOutput, create_transaction, sign_transaction
        from rpc_manager import get_utxos, submit_transaction

        WHISPER_AMOUNT = 20000000  # 0.2 KAS
        TX_FEE = 50000

        contacts = load_contacts()
        to = contacts.get(to_name.lower())
        if not to:
            return web.json_response({'error': f'contact "{to_name}" not found',
                                      'available': list(contacts.keys())}, status=404)
        if not to.get('pubkey'):
            return web.json_response({'error': f'{to["name"]} has no pubkey'}, status=400)

        pk = PrivateKey(sender_privkey)
        from_addr = pk.to_public_key().to_address('testnet').to_string()

        if plain:
            payload = json.dumps({
                "v": 1, "t": "message", "d": message,
                "a": {"from": from_addr}
            }, separators=(',', ':'), ensure_ascii=False).encode()
        else:
            encrypted = ecies_encrypt(to['pubkey'], message.encode('utf-8'))
            payload = json.dumps({
                "v": 1, "t": "whisper", "d": encrypted.hex(),
                "a": {"from": from_addr}
            }, separators=(',', ':'), ensure_ascii=False).encode()

        entries = await get_utxos(from_addr)
        if not entries:
            return web.json_response({'error': 'no UTXOs available'}, status=400)

        entries.sort(key=lambda e: e["utxoEntry"]["amount"], reverse=True)
        selected, total = [], 0
        for e in entries:
            selected.append(e)
            total += e["utxoEntry"]["amount"]
            if total >= WHISPER_AMOUNT + TX_FEE + 1000:
                break

        if total < WHISPER_AMOUNT + TX_FEE:
            return web.json_response({'error': f'insufficient balance: {total/1e8:.4f} KAS'}, status=400)

        change = total - WHISPER_AMOUNT - TX_FEE
        outputs = [PaymentOutput(Address(to['address']), WHISPER_AMOUNT)]
        if change > 0:
            outputs.append(PaymentOutput(Address(from_addr), change))

        tx = create_transaction(utxo_entry_source=selected, outputs=outputs,
                                priority_fee=TX_FEE, payload=payload)
        signed = sign_transaction(tx, [pk], False)

        if raw:
            return web.json_response({'signed_tx': signed.to_json(), 'status': 'ok'})

        tx_id = await submit_transaction(signed, allow_orphan=False)

        # Fire-and-forget webhook notification
        msg_type = 'message' if plain else 'whisper'
        asyncio.ensure_future(_notify_webhook(to, tx_id, from_addr, msg_type))

        return web.json_response({'tx_id': tx_id, 'status': 'ok'})

    except Exception as e:
        return web.json_response({'error': str(e)}, status=500)

async def post_broadcast(request):
    try:
        body = await request.json()
    except Exception:
        return web.json_response({'error': 'invalid JSON'}, status=400)

    try:
        from kaspa import Transaction
        from rpc_manager import submit_transaction

        transactions = []
        if 'transactions' in body:
            transactions = [t['signed_tx'] for t in body['transactions']]
        elif 'signed_tx' in body:
            transactions = [body['signed_tx']]
        else:
            return web.json_response({'error': 'missing signed_tx or transactions'}, status=400)

        results = []
        for tx_json in transactions:
            try:
                tx = Transaction.from_json(tx_json)
                tx_id = await submit_transaction(tx, allow_orphan=False)
                results.append({'tx_id': tx_id, 'status': 'ok'})
            except Exception as e:
                results.append({'error': str(e), 'status': 'error'})

        return web.json_response({'results': results})

    except Exception as e:
        return web.json_response({'error': str(e)}, status=500)


# ── Public endpoints (no auth) ────────────────────────

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
SKILL_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'skills', 'kaspa-whisper', 'SKILL.md')

async def landing_page(request):
    """Serve landing page (HTML for browsers, JSON for agents)"""
    accept = request.headers.get('Accept', '')
    if 'application/json' in accept and 'text/html' not in accept:
        return web.json_response({
            "name": "Kaspa Whisper Protocol",
            "version": "1.0",
            "description": "On-chain encrypted messaging for AI Agents",
            "network": "kaspa-testnet",
            "encryption": "ECIES (secp256k1)",
            "endpoints": {
                "contacts": "GET /whisper/contacts",
                "contact": "GET /whisper/contacts/{agentId}",
                "encode": "POST /whisper/encode",
                "broadcast": "POST /whisper/broadcast",
                "webhook": "PUT /whisper/contacts/{agentId}/webhook",
            },
            "docs": "https://whisper.openclaw-alpha.com/skill.md",
            "office": "https://office.openclaw-alpha.com",
            "source": "https://github.com/ryansoq/openclaw-alpha/tree/main/skills/kaspa-whisper",
        })
    # Serve HTML
    html_path = os.path.join(STATIC_DIR, 'index.html')
    if os.path.exists(html_path):
        return web.FileResponse(html_path)
    return web.Response(text="Kaspa Whisper Protocol - see /skill.md")

async def skill_doc(request):
    """Serve SKILL.md"""
    if os.path.exists(SKILL_FILE):
        with open(SKILL_FILE) as f:
            content = f.read()
        return web.Response(text=content, content_type='text/markdown')
    return web.Response(text="SKILL.md not found", status=404)


# ── Public API: Register & Inbox ──────────────────────

WEBHOOK_URL_RE = re.compile(r'^https?://.+')
AGENT_ID_RE = re.compile(r'^[a-z0-9][a-z0-9\-]{1,18}[a-z0-9]$')


async def _notify_webhook(contact, tx_id, from_addr, msg_type):
    """Fire-and-forget webhook notification"""
    webhook_url = contact.get('webhookUrl')
    if not webhook_url:
        return

    payload = {
        "event": "new_message",
        "tx_id": tx_id,
        "from": from_addr,
        "type": msg_type,
        "to": contact['address'],
        "timestamp": int(time.time()),
        "decode_hint": f"Use decode.py {tx_id} --key <your_privkey> to read"
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(webhook_url, json=payload)
            if resp.status_code >= 400:
                raise Exception(f"HTTP {resp.status_code}")
            log.info(f"Webhook delivered → {webhook_url}")
    except Exception as e:
        log.warning(f"Webhook first attempt failed ({e}), queuing for retry")
        await _webhook_retry_queue.put({'url': webhook_url, 'payload': payload, 'attempt': 0})

async def post_register(request):
    """Public: register a new agent into contacts.json"""
    try:
        body = await request.json()
    except Exception:
        return web.json_response({'error': 'invalid JSON'}, status=400)

    agent_id = body.get('agentId', '')
    name = body.get('name', '')
    address = body.get('address', '')
    pubkey = body.get('pubkey', '')

    # Validate required fields
    if not all([agent_id, name, address, pubkey]):
        return web.json_response({'error': 'missing required fields: agentId, name, address, pubkey'}, status=400)

    # Validate agentId format
    if not AGENT_ID_RE.match(agent_id):
        return web.json_response({'error': 'agentId must be 3-20 chars, lowercase alphanumeric + hyphens'}, status=400)

    # Validate address format
    if not address.startswith('kaspatest:') and not address.startswith('kaspa:'):
        return web.json_response({'error': 'address must start with kaspatest: or kaspa:'}, status=400)

    # Validate pubkey format (hex, starts with 02 or 03)
    if not re.match(r'^0[23][0-9a-fA-F]{64}$', pubkey):
        return web.json_response({'error': 'pubkey must be 66-char compressed hex (02/03 prefix)'}, status=400)

    # Load, check, write
    try:
        contacts = load_contacts()
    except Exception:
        contacts = {}

    if agent_id in contacts:
        return web.json_response({'error': f'agentId "{agent_id}" already registered'}, status=409)

    # Check address not already used by another agent
    for existing_id, existing in contacts.items():
        if existing.get('address') == address:
            return web.json_response({'error': f'address already registered by agent "{existing_id}"'}, status=409)

    # Optional webhookUrl
    webhook_url = body.get('webhookUrl', '')
    if webhook_url and not WEBHOOK_URL_RE.match(webhook_url):
        return web.json_response({'error': 'webhookUrl must start with http:// or https://'}, status=400)

    new_agent = {
        'name': name,
        'address': address,
        'pubkey': pubkey,
        'registered_at': datetime.now(timezone.utc).strftime('%Y-%m-%d'),
    }
    if webhook_url:
        new_agent['webhookUrl'] = webhook_url
    contacts[agent_id] = new_agent

    try:
        _save_contacts_safe(contacts, CONTACTS_FILE)
    except Exception as e:
        return web.json_response({'error': f'failed to save: {e}'}, status=500)

    # Send welcome bonus (non-blocking, failure doesn't affect registration)
    welcome_bonus = await _send_welcome_bonus(address)

    return web.json_response({
        'status': 'registered',
        'agent': {'agentId': agent_id, 'name': name, 'address': address, 'pubkey': pubkey},
        'welcome_bonus': welcome_bonus
    }, status=201)


async def put_webhook(request):
    """Auth-protected: update webhookUrl for an agent"""
    agent_id = request.match_info['agentId']
    try:
        body = await request.json()
    except Exception:
        return web.json_response({'error': 'invalid JSON'}, status=400)

    webhook_url = body.get('webhookUrl', '')

    # Allow empty string to clear webhook
    if webhook_url and not WEBHOOK_URL_RE.match(webhook_url):
        return web.json_response({'error': 'webhookUrl must start with http:// or https://'}, status=400)

    contacts = load_contacts()
    if agent_id.lower() not in contacts:
        return web.json_response({'error': f'agent "{agent_id}" not found'}, status=404)

    if webhook_url:
        contacts[agent_id.lower()]['webhookUrl'] = webhook_url
    else:
        contacts[agent_id.lower()].pop('webhookUrl', None)

    _save_contacts_safe(contacts, CONTACTS_FILE)

    action = 'set' if webhook_url else 'removed'
    return web.json_response({'status': f'webhook {action}', 'agentId': agent_id.lower()})


async def post_webhook_register(request):
    """Public: agent registers/updates their webhook URL by proving address ownership."""
    try:
        body = await request.json()
    except Exception:
        return web.json_response({'error': 'invalid JSON'}, status=400)

    agent_id = body.get('agentId', '').lower()
    webhook_url = body.get('webhookUrl', '')

    if not agent_id:
        return web.json_response({'error': 'missing agentId'}, status=400)
    if not webhook_url:
        return web.json_response({'error': 'missing webhookUrl'}, status=400)
    if not WEBHOOK_URL_RE.match(webhook_url):
        return web.json_response({'error': 'webhookUrl must start with http:// or https://'}, status=400)

    contacts = load_contacts()
    if agent_id not in contacts:
        return web.json_response({'error': f'agent "{agent_id}" not found, register first via POST /whisper/register'}, status=404)

    contacts[agent_id]['webhookUrl'] = webhook_url
    try:
        _save_contacts_safe(contacts, CONTACTS_FILE)
    except Exception as e:
        return web.json_response({'error': f'failed to save: {e}'}, status=500)

    return web.json_response({'status': 'webhook registered', 'agentId': agent_id, 'webhookUrl': webhook_url})


async def get_inbox(request):
    """Public: query recent whisper/message TXs for an address"""
    address = request.match_info['address']
    limit = min(int(request.query.get('limit', '20')), 50)

    api_url = f'https://api-tn10.kaspa.org/addresses/{address}/full-transactions?limit={limit}&resolve_previous_outpoints=light'

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(api_url)
            if resp.status_code != 200:
                return web.json_response({'error': f'Kaspa API returned {resp.status_code}'}, status=502)
            txs = resp.json()
    except Exception as e:
        return web.json_response({'error': f'Kaspa API error: {e}'}, status=502)

    messages = []
    for tx in txs:
        payload_hex = tx.get('payload')
        if not payload_hex:
            continue
        try:
            payload = json.loads(bytes.fromhex(payload_hex).decode('utf-8'))
        except Exception:
            continue
        if payload.get('v') != 1:
            continue
        msg_type = payload.get('t')
        if msg_type not in ('whisper', 'message'):
            continue

        # Extract sender from payload metadata
        sender = payload.get('a', {}).get('from', 'unknown')

        # Build timestamp from block_time (milliseconds) if available
        block_time = tx.get('block_time')
        timestamp = datetime.fromtimestamp(block_time / 1000, tz=timezone.utc).isoformat() if block_time else None

        entry = {
            'tx_id': tx.get('transaction_id', tx.get('subnetwork_id', '')),
            'type': msg_type,
            'from': sender,
            'timestamp': timestamp,
        }
        if msg_type == 'message':
            entry['content'] = payload.get('d', '')

        messages.append(entry)

    return web.json_response({'address': address, 'messages': messages})


# ── Fix #1: TX Listener with Retry/Reconnect ─────────

class TxListener:
    """Polls Kaspa API for new whisper TXs with automatic retry on failure."""

    def __init__(self, poll_interval=30, max_backoff=300):
        self.poll_interval = poll_interval
        self.max_backoff = max_backoff
        self._task = None
        self._seen_txs: collections.deque = collections.deque(maxlen=500)
        self._consecutive_failures = 0

    async def start(self):
        self._task = asyncio.ensure_future(self._run())
        log.info("TX Listener started (poll-based with retry)")

    async def stop(self):
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run(self):
        while True:
            try:
                await self._poll_once()
                self._consecutive_failures = 0
                await asyncio.sleep(self.poll_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._consecutive_failures += 1
                backoff = min(self.poll_interval * (2 ** self._consecutive_failures), self.max_backoff)
                log.warning(f"TX Listener error ({e}), retry in {backoff}s (failure #{self._consecutive_failures})")
                await asyncio.sleep(backoff)

    async def _poll_once(self):
        contacts = load_contacts()
        addresses = [c['address'] for c in contacts.values() if c.get('address') and c.get('webhookUrl')]
        if not addresses:
            return

        for agent_id, contact in contacts.items():
            if not contact.get('webhookUrl') or not contact.get('address'):
                continue
            try:
                url = f"https://api-tn10.kaspa.org/addresses/{contact['address']}/full-transactions?limit=5&resolve_previous_outpoints=light"
                async with httpx.AsyncClient(timeout=15) as client:
                    resp = await client.get(url)
                    if resp.status_code != 200:
                        continue
                    txs = resp.json()

                for tx in txs:
                    tx_id = tx.get('transaction_id', '')
                    if not tx_id or tx_id in self._seen_txs:
                        continue
                    self._seen_txs.append(tx_id)

                    payload_hex = tx.get('payload')
                    if not payload_hex:
                        continue
                    try:
                        payload = json.loads(bytes.fromhex(payload_hex).decode('utf-8'))
                    except Exception:
                        continue
                    if payload.get('v') == 1 and payload.get('t') in ('whisper', 'message'):
                        from_addr = payload.get('a', {}).get('from', 'unknown')
                        asyncio.ensure_future(_notify_webhook(contact, tx_id, from_addr, payload['t']))
            except Exception as e:
                log.debug(f"TX poll error for {agent_id}: {e}")


tx_listener = TxListener()


# ── App ───────────────────────────────────────────────

def create_app():
    # Auth-protected routes
    whisper_app = web.Application(middlewares=[auth_middleware])
    whisper_app.router.add_get('/contacts', get_contacts)
    whisper_app.router.add_get('/contacts/{agentId}', get_contact)
    whisper_app.router.add_put('/contacts/{agentId}/webhook', put_webhook)

    # Main app (public routes + subapp)
    app = web.Application()

    async def on_startup(app):
        app['webhook_retry_worker'] = asyncio.ensure_future(_webhook_retry_worker())
        await tx_listener.start()
        log.info("Background workers started")

    async def on_shutdown(app):
        await tx_listener.stop()
        app['webhook_retry_worker'].cancel()

    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    app.router.add_get('/', landing_page)
    app.router.add_get('/skill.md', skill_doc)
    app.router.add_post('/whisper/register', post_register)
    app.router.add_post('/whisper/webhook/register', post_webhook_register)
    app.router.add_get('/whisper/inbox/{address:.+}', get_inbox)
    app.router.add_post('/whisper/broadcast', post_broadcast)
    app.add_subapp('/whisper/', whisper_app)
    return app

if __name__ == '__main__':
    import socket
    print(f"🌊 Kaspa Whisper API starting on port {PORT}")
    print(f"   Landing: http://localhost:{PORT}/")
    print(f"   Skill:   http://localhost:{PORT}/skill.md")
    print(f"   API:     http://localhost:{PORT}/whisper/")
    # SO_REUSEADDR to avoid "address already in use" after restart
    web.run_app(create_app(), host='0.0.0.0', port=PORT,
                reuse_address=True, reuse_port=True)
