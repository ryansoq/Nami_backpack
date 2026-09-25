"""真 hemibrain 接線 -> 稀疏 A -> brian2 LIF -> 線性讀出 heading。
資料: hemibrain v1.2 公開 adjacency dump（無需 token）。"""
import pandas as pd, numpy as np, re, pickle, pathlib
D=pathlib.Path('/home/ymchang/nami-backpack/data/hemibrain/exported-traced-adjacencies-v1.2')

n=pd.read_csv(D/'traced-neurons.csv')
cx=n[n['type'].astype(str).str.match('^(EPG|EPGt|PEG|Delta7|PEN_a|PEN_b)')].copy()

def glom(inst):
    m=re.search(r'_([LR])(\d)', str(inst))
    return (m.group(1), int(m.group(2))) if m else (None,None)
cx[['side','gi']]=cx['instance'].apply(lambda s: pd.Series(glom(s)))
cx=cx.dropna(subset=['gi']).copy(); cx['gi']=cx['gi'].astype(int)

# PB glomerulus -> heading 角度。左右各 8-9 個 glomeruli 是同一個環的兩份拷貝。
cx['theta']=2*np.pi*((cx['gi']-1)%8)/8.0
cx['fam']=cx['type'].str.replace(r'\(.*','',regex=True)      # EPG/EPGt/PEG/Delta7/PEN_a/PEN_b
cx=cx.sort_values(['fam','side','gi']).reset_index(drop=True)
idx={b:i for i,b in enumerate(cx['bodyId'])}
N=len(cx); print(f"CX 神經元（有 glomerulus 標記）: {N}")
print(cx.groupby('fam').size().to_string())

# --- 連線：只留 CX 內部
conn=pd.read_csv(D/'traced-total-connections.csv')
print(f"全腦連線: {len(conn):,}")
c=conn[conn['bodyId_pre'].isin(idx) & conn['bodyId_post'].isin(idx)].copy()
print(f"CX 內部連線: {len(c):,}   總突觸數: {c['weight'].sum():,}")

# --- 符號：hemibrain 這份 dump 沒有 nt_type，用型別的已知生化指定
#     Delta7 = GABA（抑制）；EPG/PEG/PEN = ACh（興奮）
fam=dict(zip(cx['bodyId'],cx['fam']))
sign=lambda b: -1.0 if fam[b]=='Delta7' else +1.0
c['pre_i']=c['bodyId_pre'].map(idx); c['post_i']=c['bodyId_post'].map(idx)
c['sgn']=c['bodyId_pre'].map(lambda b: sign(b))
c['sw']=c['weight']*c['sgn']

A=np.zeros((N,N),dtype=np.float32)
A[c['pre_i'],c['post_i']]=c['sw']
nz=(A!=0).sum()
print(f"A: {N}x{N}  非零 {nz}  稀疏度 {100*nz/(N*N):.2f}%")
print(f"  興奮邊 {(A>0).sum()}  抑制邊 {(A<0).sum()}")

pickle.dump({'A':A,'cx':cx}, open('cx.pkl','wb'))
print("-> cx.pkl")
