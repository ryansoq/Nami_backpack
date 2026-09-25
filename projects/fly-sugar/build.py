"""Shiu 式 LIF：真接線 + 真 nt 符號 + 一個全腦共用的每突觸電壓 q。無訓練。"""
import pandas as pd, numpy as np, scipy.sparse as sp, pickle
D='/home/ymchang/nami-backpack/data/malecns/'
a=pd.read_feather(D+'annotations.feather')
nt=pd.read_feather(D+'nt.feather').drop_duplicates('body')[['body','consensus_nt']]
a=a.merge(nt,left_on='bodyId',right_on='body',how='left')
a=a[a['superclass'].notna()].reset_index(drop=True)
idx={b:i for i,b in enumerate(a['bodyId'])}; N=len(a)

EXC={'acetylcholine'}; INH={'gaba','glutamate'}
def sgn(x):
    if not isinstance(x,str): return 0.0
    x=x.lower()
    return 1.0 if x in EXC else (-1.0 if x in INH else 0.0)
a['sgn']=a['consensus_nt'].map(sgn)

e=pd.read_feather(D+'edges.feather')
e=e[e['body_pre'].isin(idx)&e['body_post'].isin(idx)]
pre=e['body_pre'].map(idx).values; post=e['body_post'].map(idx).values
sg=a['sgn'].values[pre]
W=sp.csr_matrix((e['weight'].values.astype(np.float32)*sg,(post,pre)),shape=(N,N))
print(f"N={N:,}  邊={W.nnz:,}  興奮={int((W.data>0).sum()):,}  抑制={int((W.data<0).sum()):,}")

cls=a['class'].astype(str).values; sub=a['subclass'].astype(str).values; ty=a['type'].astype(str).values
groups={
 'taste_all'   : np.where(cls=='gustatory')[0],
 'taste_bristle': np.where(np.isin(sub,['taste bristle','taste peg','labellar bristle']))[0],
 'mech_bristle': np.where(sub=='mechanosensory bristle')[0],   # 對照：不同感覺模態
 'MN9'         : np.where(ty=='MN9')[0],
 'MN11'        : np.where(np.isin(ty,['MN11D','MN11V']))[0],
 'MN_all'      : np.where(pd.Series(ty).str.match(r'^MN\d').values)[0],
}
for k,v in groups.items(): print(f"  {k:14s} {len(v):5d}")
pickle.dump({'W':W,'groups':groups,'ty':ty,'N':N},open('brain.pkl','wb'))
print("-> brain.pkl")
