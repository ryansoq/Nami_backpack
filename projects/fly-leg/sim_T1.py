"""前向模擬 T1。★ 先寫死判準，跑完才看，不准事後改。

  判準1 熵化：運動神經元輸出要有明確主頻（不是雜訊）
  判準2 相位要「散開」—— 若 173 顆全部同相，那只是在轉播輸入，
        不是步態。步態的定義就是不同肌肉在不同時間出力。
  判準3 打散接線後，判準2 要消失。留得住才代表接線在做事。
"""
import numpy as np, pickle, scipy.sparse as sp, sys
np.random.seed(0)
d=pickle.load(open('T1.pkl','rb')); W=d['W']; t1=d['t1']; mot=d['mot']
N=W.shape[0]
G=float(sys.argv[1]) if len(sys.argv)>1 else 0.004
DRIVE=sys.argv[2] if len(sys.argv)>2 else 'rhythm'
SHUF=len(sys.argv)>3 and sys.argv[3]=='shuffle'

if SHUF:   # 對照：保留每顆的出入度分佈，只打散「誰連誰」
    rng=np.random.default_rng(1); W=W.tocoo()
    perm=rng.permutation(N)
    W=sp.csr_matrix((W.data,(perm[W.row],perm[W.col])),shape=(N,N))

dt,T = 1.0, 4000.0          # ms
tau   = 20.0
steps = int(T/dt)
r=np.zeros(N,dtype=np.float32)
drv_idx=np.where(t1['superclass'].values=='vnc_intrinsic')[0]
rng=np.random.default_rng(2); drv_sel=rng.choice(drv_idx,400,replace=False)
F=5.0                        # Hz
rec=np.zeros((steps,len(mot)),dtype=np.float32)
for s in range(steps):
    t=s*dt
    I=np.zeros(N,dtype=np.float32)
    if DRIVE=='rhythm': I[drv_sel]=3.0*(1+np.sin(2*np.pi*F*t/1000.0))
    elif DRIVE=='tonic': I[drv_sel]=3.0
    x=W.dot(r)*G + I + 0.35
    r += (dt/tau)*(-r + np.maximum(x,0))
    if not np.isfinite(r).all() or r.max()>1e6:
        print(f"  發散於 step {s}（G 太大）"); raise SystemExit
    rec[s]=r[mot]

burn=int(1000/dt); R=rec[burn:]
print(f"G={G} drive={DRIVE} shuffled={SHUF}")
print(f"  運動神經元平均活動 {R.mean():.4f}  最大 {R.max():.4f}  有活動的 {(R.mean(0)>1e-4).sum()}/{len(mot)}")
if R.max()<1e-5: print("  全滅"); raise SystemExit
if R.max()>1e4:  print("  爆掉"); raise SystemExit

# 主頻
Rz=R-R.mean(0); fs=1000.0/dt
F_=np.fft.rfft(Rz,axis=0); freq=np.fft.rfftfreq(len(R),1/fs)
pw=(np.abs(F_)**2).sum(1); pw[0]=0
k=pw.argmax(); print(f"  主頻 {freq[k]:.2f} Hz  （輸入 {F} Hz）")
band=pw[max(1,k-2):k+3].sum()/pw[1:].sum()
print(f"  主頻集中度 {band*100:.1f}%  (越高越像乾淨的節律)")

# 相位散佈
act=Rz.std(0)>1e-6
ph=np.angle(F_[k][act])
z=np.abs(np.exp(1j*ph).mean())
print(f"  ★ 相位集中度 R = {z:.3f}   (1.0=全部同相=只是轉播；越小越散=真的有相位結構)")
print(f"     參與計算的運動神經元 {act.sum()}")
hist=np.histogram(np.degrees(ph)%360,bins=8,range=(0,360))[0]
print("     相位分佈(8格):", hist.tolist())
