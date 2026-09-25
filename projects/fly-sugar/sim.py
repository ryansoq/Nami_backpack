"""★ 判準寫在前面（Shiu 式設計，這次有對照組）：
  ①  刺激味覺神經元 -> MN9 要發火
  ②  改刺激機械感覺（同樣數量）-> MN9 要幾乎不發火  ← 特異性
  ③  打散重連 -> ① 要消失
  只有三個都成立才算成功。
"""
import numpy as np, pickle, scipy.sparse as sp, sys
d=pickle.load(open('brain.pkl','rb')); W=d['W']; g=d['groups']; N=d['N']
Q      = float(sys.argv[1]) if len(sys.argv)>1 else 0.30   # 每突觸 mV
STIM   = sys.argv[2] if len(sys.argv)>2 else 'taste_bristle'
SHUF   = len(sys.argv)>3 and sys.argv[3]=='shuffle'
RATE   = 150.0    # 被刺激的神經元發火率 Hz
if SHUF:
    rng=np.random.default_rng(1); C=W.tocoo(); p=rng.permutation(N)
    W=sp.csr_matrix((C.data,(p[C.row],p[C.col])),shape=(N,N))

dt=0.5; T=300.0; steps=int(T/dt)          # ms
TAU=20.0; VR=-52.0; VTH=-45.0; VRESET=-52.0; REF=2.2
V=np.full(N,VR,dtype=np.float32)
ref=np.zeros(N,dtype=np.float32)
stim=g[STIM]
nstim=len(g['taste_bristle'])             # 對照組用同樣數量，公平比較
if STIM!='taste_bristle':
    stim=np.random.default_rng(7).choice(g[STIM],min(nstim,len(g[STIM])),replace=False)
cnt=np.zeros(N,dtype=np.int32)
rng=np.random.default_rng(0)
prev=np.zeros(N,dtype=np.float32)      # 上一步誰發火 -> 這一步的輸入
for s in range(steps):
    fire=prev.copy()                   # ★ 網路自己的 spike 要餵回去
    fire[stim]=np.maximum(fire[stim],
        (rng.random(len(stim))<RATE*dt/1000.0).astype(np.float32))
    inj=W.dot(fire)*Q
    live=ref<=0
    V[live]+= dt/TAU*(VR-V[live]) + inj[live]
    ref[~live]-=dt
    sp_now=(V>VTH)&live
    cnt+=sp_now
    V[sp_now]=VRESET; ref[sp_now]=REF
    prev=sp_now.astype(np.float32)

def hz(ix): return cnt[ix].sum()/len(ix)/(T/1000.0) if len(ix) else 0.0
print(f"Q={Q}  刺激={STIM}({len(stim)} 顆)  shuffled={SHUF}")
print(f"  全腦總 spike {cnt.sum():,}   有發火的神經元 {int((cnt>0).sum()):,}/{N:,}")
print(f"  ★ MN9      {hz(g['MN9']):7.2f} Hz")
print(f"    MN11     {hz(g['MN11']):7.2f} Hz")
print(f"    MN_all   {hz(g['MN_all']):7.2f} Hz")
print(f"    全腦平均 {cnt.sum()/N/(T/1000.0):7.2f} Hz")
