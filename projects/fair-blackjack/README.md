# 公平 21 點: provably fair blackjack (web, step A before a vprog)

Ryan 2026-09-28, right after the vprog tic-tac-toe match: 「那妳是不是可以根據這個設計21點」.
Published: https://claude.ai/artifact/SmLXc2dR7tHAimsh9pA5Zq

Commit–reveal: the house publishes SHA256(serverSeed) before the deal. The player's clientSeed
cuts the deck. Deck = Fisher–Yates with j = int(SHA256("server:client:nonce:i")[:8],16) % (i+1),
i = 51..1. After the hand the server seed is revealed and the page recomputes every dealt card.
A cheat-mode switch has the dealer swap a card when about to bust. Verification flags it.

Rules: one 52-card deck reshuffled per hand, dealer stands on all 17 (S17), BJ pays 3:2,
double on the first two cards, no split, no insurance.

Tests (2026-09-28): `verify_ref.py` (independent hashlib implementation) matched the page's deck
on 20/20 seeds. `play.cjs` honest: 25/25 hands clean. Cheat: 9 swaps in 40 hands, 9/9 caught, 0 missed.

Limit: house and player share one page, so this demonstrates the protocol, not trust separation.
The vprog version (step B) would put the commitment, the client seed and the settlement proof on Kaspa.
