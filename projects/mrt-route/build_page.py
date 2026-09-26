import json
d = json.load(open('mrt-data.json'))
d.pop('segFit', None)
d['schema'] = json.load(open('schema.json'))
d['model'] = {"wait": 0, "penalty": 3, "board": 1, "valN": 28, "valMae": 1.6, "valSame": "27/28",
              "note": "penalty 3 set as a half-headway prior after first seeing val at penalty 1 (24/28)"}
src = open('page.src.html').read()
src = src.replace('/*DATA*/', json.dumps(d, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/'))
src = src.replace('/*ROUTER*/', open('router.js').read())
open('mrt-route.html', 'w').write(src)
print(len(src.encode()), 'bytes')
