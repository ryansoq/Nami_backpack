"""Independent re-implementation of the deck algorithm (Python hashlib), to check the page."""
import hashlib, sys, json
def shuffle(server, client, nonce):
    d = list(range(52))
    for i in range(51, 0, -1):
        h = hashlib.sha256(f"{server}:{client}:{nonce}:{i}".encode()).hexdigest()
        j = int(h[:8], 16) % (i + 1)
        d[i], d[j] = d[j], d[i]
    return d
cases = json.load(sys.stdin)
bad = sum(1 for c in cases if shuffle(c['s'], c['c'], c['n']) != c['deck'])
print(f"python vs page decks: {len(cases)} cases, {bad} mismatches")
