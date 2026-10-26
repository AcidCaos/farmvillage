"""Evaluate FarmConfig.swf (the client's prebuilt "buildtime" indexes) into data.

Read-only. Usage, from this folder:
  curl -o FarmConfig.swf http://127.0.0.1:<port>/xml/gz/v855098/FarmConfig.swf
  python3 -I evalconfig.py FarmConfig.swf farmconfig.pkl
Prints the top-level properties (typesHash, market3TypesHash, classNameHash,
questCategories...) and pickles them. Example: market3TypesHash['seed']['seedfisherman']
is the list of seeds the Market shows on Lighthouse Cove.
"""
import os
import sys, pickle; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import abcdis
abcs, index = abcdis.load(sys.argv[1])
a = abcs[0]; ai, mi = index['FarmConfig.<init>']
code = a.bodies[mi]; r = abcdis.R(code); st = []; props = {}
while r.p < len(code):
    op = r.u8()
    if op == 0x2C: st.append(a.strings[r.u30()])
    elif op == 0x56:
        n = r.u30(); v = st[len(st)-n:]; del st[len(st)-n:]; st.append(v)
    elif op == 0x55:
        n = r.u30(); kv = st[len(st)-2*n:]; del st[len(st)-2*n:]
        st.append({kv[i]: kv[i+1] for i in range(0, len(kv), 2)})
    elif op == 0xD0: st.append('this')
    elif op == 0x30: st.pop()
    elif op == 0x68:
        name = a.short(r.u30()); v = st.pop(); st.pop(); props[name] = v
    elif op == 0x49: r.u30(); st.pop()
    elif op == 0x60: r.u30(); st.append('lex')
    elif op == 0x4F: r.u30(); n = r.u30(); del st[len(st)-n-1:]
    elif op == 0x47: break
    else: raise SystemExit('unhandled op %x at %d' % (op, r.p))
pickle.dump(props, open(sys.argv[2], 'wb'))
print({k: (type(v).__name__, len(v)) for k, v in props.items()})
