"""真正的 CPG：Pugliese et al. 2025 找到的三顆神經元，接線與符號全部來自 MaleCNS。
   E1=IN17A001(ACh) E2=INXXX466(ACh) I1=IN16B036(Glu) I2=IN19A007(GABA)
   指令神經元 DNg100(ACh)。每節 2 顆 = 六隻腳各一套。"""
import pandas as pd, numpy as np, pickle
D='/home/ymchang/nami-backpack/data/malecns/'
a=pd.read_feather(D+'annotations.feather')
nt=pd.read_feather(D+'nt.feather').drop_duplicates('body')[['body','consensus_nt']]
a=a.merge(nt,left_on='bodyId',right_on='body',how='left')
NAME={'IN17A001':'E1','INXXX466':'E2','IN16B036':'I1','IN19A007':'I2','DNg100':'CMD'}
sel=a[a['type'].astype(str).isin(NAME)|a['mancType'].astype(str).isin(NAME)].copy()
sel['role']=sel.apply(lambda r: NAME.get(str(r['type']), NAME.get(str(r['mancType']),'?')),axis=1)
sel['seg']=sel['somaNeuromere'].astype(str)
sel['side']=sel['somaSide'].astype(str)
sel=sel.sort_values(['role','seg','side']).reset_index(drop=True)
ids=list(sel['bodyId']); idx={b:i for i,b in enumerate(ids)}; N=len(ids)
print(f"=== 節點 {N} 顆 ===")
for _,r in sel.iterrows():
    print(f"  {r['role']:4s} {str(r['type'])[:10]:10s} seg={r['seg']:3s} side={r['side']:4s} nt={r['consensus_nt']}")

e=pd.read_feather(D+'edges.feather')
sub=e[e['body_pre'].isin(idx)&e['body_post'].isin(idx)]
print(f"\n=== 這 {N} 顆之間的真實連線 {len(sub)} 條，總突觸 {int(sub['weight'].sum())} ===")
EXC={'acetylcholine'}; INH={'gaba','glutamate'}
sg=lambda x: 1.0 if str(x).lower() in EXC else (-1.0 if str(x).lower() in INH else 0.0)
sel['sgn']=sel['consensus_nt'].map(sg)
W=np.zeros((N,N))
rows=[]
for _,r in sub.iterrows():
    i,j=idx[r['body_pre']],idx[r['body_post']]
    W[j,i]=r['weight']*sel['sgn'].iloc[i]
    rows.append((sel['role'].iloc[i],sel['seg'].iloc[i],sel['side'].iloc[i],
                 sel['role'].iloc[j],sel['seg'].iloc[j],sel['side'].iloc[j],int(r['weight']),sel['sgn'].iloc[i]))
rows.sort(key=lambda x:-x[6])
print(f"{'pre':>18} -> {'post':<18} {'syn':>5} sign")
for r in rows[:22]:
    print(f"{r[0]+' '+r[1]+r[2][:1]:>18} -> {r[3]+' '+r[4]+r[5][:1]:<18} {r[6]:5d} {'+' if r[7]>0 else '-'}")
print(f"\n非零權重 {int((W!=0).sum())}  興奮 {int((W>0).sum())}  抑制 {int((W<0).sum())}")
pickle.dump({'W':W,'sel':sel,'ids':ids},open('real_cpg.pkl','wb'))
print("-> real_cpg.pkl")
