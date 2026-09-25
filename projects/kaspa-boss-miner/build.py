#!/usr/bin/env python3
"""Inline khh.js into the game page -> game.html (single file, publishable)."""
import pathlib
d = pathlib.Path(__file__).parent
src = (d / 'game.src.html').read_text()
(d / 'game.html').write_text(src.replace('/*KHH*/', (d / 'khh.js').read_text()))
print('game.html', (d / 'game.html').stat().st_size, 'bytes')
