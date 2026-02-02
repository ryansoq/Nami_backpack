# 🌊 ShioKaze (潮風) - Nami's Kaspa Miner

A gentle sea breeze that mines Kaspa blocks.

Built by **Nami (波浪)** - 2026

## Features

- ✨ **NumPy 優化 HeavyHash** - 比原版快 ~400x
- ✨ **矩陣緩存** - 同區塊自動重複使用
- ✨ **觀察模式** - 快速 template 循環，適合測試
- ✨ **詳細統計** - hashrate、cache hit rate 等
- ✨ **雙網支援** - Testnet 和 Mainnet

## Requirements

```bash
pip install grpcio grpcio-tools numpy pycryptodome
```

Also needs proto stubs from `kaspa-pminer`:
- `kaspa_pb2.py`
- `kaspa_pb2_grpc.py`
- `kaspa_miner_multi_core.py`

## Usage

### Testnet (觀察模式)
```bash
python3 shiokaze.py --testnet --observe --wallet kaspatest:qr...
```

### Testnet (一般模式)
```bash
python3 shiokaze.py --testnet --wallet kaspatest:qr...
```

### Mainnet
```bash
python3 shiokaze.py --wallet kaspa:qr...
```

### Options

| Option | Description |
|--------|-------------|
| `--wallet, -w` | Mining reward wallet address (required) |
| `--address, -a` | kaspad gRPC address (default: auto) |
| `--testnet, -t` | Use testnet (port 16210) |
| `--observe, -o` | Observe mode (max_nonce=2000) |
| `--max-nonce, -n` | Max nonce per template (default: 50000) |
| `--debug, -d` | Enable debug output |

## Architecture

```
┌─────────────┐     gRPC      ┌─────────────┐
│  ShioKaze   │ ◄───────────► │   kaspad    │
│   Miner     │               │   (node)    │
└──────┬──────┘               └─────────────┘
       │
       ▼
┌─────────────┐
│ WaveHasher  │ ← NumPy + Cache
│ (HeavyHash) │
└─────────────┘
```

## Performance

| Version | Hashrate | Improvement |
|---------|----------|-------------|
| Original Python | ~13 H/s | 1x |
| ShioKaze (NumPy) | ~5000 H/s | ~400x |

## Name Origin

**潮風 (ShioKaze)** means "sea breeze" in Japanese.

Like a gentle breeze from the ocean, this miner quietly works in the background, riding the waves of Kaspa's BlockDAG.

## License

MIT - Made with 🌊 by Nami
