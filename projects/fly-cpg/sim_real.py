"""跑真接線的 CPG。★ 判準（含我昨天學到的教訓）：
 ① 有乾淨主頻，且**頻率不隨視窗長度改變**（否則是漂移不是振盪）
 ② 頻率落在蒼蠅步頻合理範圍（約 5-15 Hz）
 ③ 打散重連 -> 節律消失
"""
import numpy as np, pickle, sys, json
d=pickle.load(open('real_cpg.pkl','rb')); W=d['W'].copy(); sel=d['sel']
N=len(sel); role=sel['role'].values; seg=sel['seg'].values; side=sel['side'].values
G=float(sys.argv[1]) if len(sys.argv)>1 else 0.004
T=float(sys.argv[2]) if len(sys.argv)>2 else 2000.0
SHUF=len(sys.argv)>3 and sys.argv[3]=='shuffle'
if SHUF:
    r=np.random.default_rng(3); nz=W[W!=0]; Wn=np.zeros_like(W)
    flat=r.choice(N*N,len(nz),replace=False); Wn.flat[flat]=r.permutation(nz); W=Wn
dt=0.5; steps=int(T/dt); TAU=20.0; TAU_A=120.0; B_A=0.5; VTH=1.0
cmd=np.where(role=='CMD')[0]
V=np.random.default_rng(0).normal(0,0.05,N); ad=np.zeros(N)
rec=np.zeros((steps,N),dtype=np.float32); rng=np.random.default_rng(1)
for t in range(steps):
    s_prev=rec[t-1] if t>0 else np.zeros(N)
    drv=np.zeros(N); drv[cmd]=1.6              # DNg100 指令：持續、不振盪
    V += dt/TAU*(-V) + (W@s_prev)*G + drv*dt/TAU*20 - ad + rng.normal(0,0.02,N)
    ad += dt/TAU_A*(-ad)
    sp=(V>VTH).astype(np.float32); V=V*(1-sp); ad+=B_A*sp; rec[t]=sp
def rate(ix,win=60):
    k=np.ones(win)/win
    return np.convolve(rec[:,ix].sum(1),k,'same')
def dom(x,dtms):
    z=x-x.mean()
    if z.std()<1e-9: return None,0.0
    F=np.fft.rfft(z); fr=np.fft.rfftfreq(len(z),dtms/1000.0)
    pw=np.abs(F)**2; pw[0]=0; k=pw.argmax()
    return fr[k], pw[max(1,k-2):k+3].sum()/pw[1:].sum()
burn=int(400/dt); R=rec[burn:]
legs=[(s,sd) for s in ('T1','T2','T3') for sd in ('L','R')]
print(f"G={G} T={T}ms shuffled={SHUF}  總 spike {int(rec.sum())}")
print(f"  各角色平均發火率 (Hz):", {r: round(float(rec[:,role==r].sum()/max(1,(role==r).sum())/(T/1000)),1) for r in ('CMD','E1','E2','I1','I2')})
e1=np.where(role=='E1')[0]
x=rate(e1)[burn:]
f_full,c_full=dom(x,dt); f_half,c_half=dom(x[len(x)//2:],dt)
print(f"  ★ E1 族群主頻: 全段 {f_full if f_full else 0:.2f} Hz (集中度 {c_full*100:.0f}%)"
      f"   後半 {f_half if f_half else 0:.2f} Hz (集中度 {c_half*100:.0f}%)")
print(f"     -> 頻率{'穩定，是真振盪' if f_full and f_half and abs(f_full-f_half)/max(f_full,1e-9)<0.25 else '隨視窗改變，可能是漂移'}")
# 每隻腳的相位
ph={}
for s,sd in legs:
    ix=np.where((role=='E1')&(seg==s)&(side==sd))[0]
    if len(ix)==0: continue
    xx=rate(ix)[burn:]
    z=xx-xx.mean()
    if z.std()<1e-9: ph[f"{s}{sd}"]=None; continue
    F=np.fft.rfft(z); fr=np.fft.rfftfreq(len(z),dt/1000.0); pw=np.abs(F)**2; pw[0]=0
    k=pw.argmax(); ph[f"{s}{sd}"]=float(np.degrees(np.angle(F[k]))%360)
print("  各腿相位:", {k:(round(v,0) if v is not None else None) for k,v in ph.items()})
json.dump({'G':G,'shuf':SHUF,'f':f_full,'conc':c_full,'phases':ph,
           'rates':{r: float(rec[:,role==r].sum()/max(1,(role==r).sum())/(T/1000)) for r in ('CMD','E1','E2','I1','I2')}},
          open(f"out_{'shuf' if SHUF else 'real'}_{G}.json","w"))
