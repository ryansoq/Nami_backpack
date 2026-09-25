"""T1（前腳）子圖：真接線 + 真 nt 符號（MaleCNS 有 consensus_nt，不用猜）。"""
import pandas as pd, numpy as np, scipy.sparse as sp, pickle
D='/home/ymchang/nami-backpack/data/malecns/'
a=pd.read_feather(D+'annotations.feather')
n=pd.read_feather(D+'nt.feather').drop_duplicates('body')[['body','consensus_nt']]
a=a.merge(n,left_on='bodyId',right_on='body',how='left')

t1=a[a['somaNeuromere']=='T1'].reset_index(drop=True)
idx={b:i for i,b in enumerate(t1['bodyId'])}
N=len(t1); print(f"T1 神經元 {N:,}")
print(t1['superclass'].value_counts().head(8).to_string())

e=pd.read_feather(D+'edges.feather')
m=e['body_pre'].isin(idx)&e['body_post'].isin(idx)
e=e[m].copy(); print(f"\nT1 內部連線 {len(e):,}  突觸 {int(e['weight'].sum()):,}")

EXC={'acetylcholine'}; INH={'gaba','glutamate'}
def sgn(x):
    if not isinstance(x,str): return 0.0
    x=x.lower()
    if x in EXC: return 1.0
    if x in INH: return -1.0
    return 0.0          # unclear / 調節性 -> 不給符號
t1['sgn']=t1['consensus_nt'].map(sgn)
print("\n符號來源（量出來的，不是我填的）:")
print(t1['sgn'].map({1.0:'excitatory',-1.0:'inhibitory',0.0:'unclear/mod/none'}).value_counts().to_string())

e['i']=e['body_pre'].map(idx); e['j']=e['body_post'].map(idx)
e['s']=e['body_pre'].map(lambda b: t1['sgn'].iloc[idx[b]])
e['sw']=e['weight']*e['s']
W=sp.csr_matrix((e['sw'].values.astype(np.float32),(e['j'].values,e['i'].values)),shape=(N,N))
print(f"\nW: {N}x{N}  nnz {W.nnz:,}  興奮邊 {(e['sw']>0).sum():,}  抑制邊 {(e['sw']<0).sum():,}  無號邊 {(e['sw']==0).sum():,}")

mot=np.where(t1['superclass'].values=='vnc_motor')[0]
sen=np.where(t1['superclass'].values=='vnc_sensory')[0]
print(f"運動神經元 {len(mot)}   感覺神經元 {len(sen)}")
print("\n運動神經元對應的肌肉（前 10）:")
for t in t1.iloc[mot]['type'].dropna().unique()[:10]: print("   ",t)

pickle.dump({'W':W,'t1':t1,'mot':mot,'sen':sen},open('T1.pkl','wb'))
print("\n-> T1.pkl")
