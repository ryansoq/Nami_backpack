"""加入真實傳導延遲：每條邊各自的延遲 = 胞體距離 / 傳導速度。
★ 但書：胞體直線距離不是軸突路徑長度，真軸突更長且彎曲 ——
   所以這些延遲是「下界」。要精確得用 neuPrint 骨架檔。"""
import pickle, numpy as np, pandas as pd, sys
d=pickle.load(open('real_cpg.pkl','rb')); W=d['W']; sel=d['sel']
D='/home/ymchang/nami-backpack/data/malecns/'
a=pd.read_feather(D+'annotations.feather')[['bodyId','somaLocation']]
m=dict(zip(a['bodyId'],a['somaLocation']))
ids=list(sel['bodyId']); N=len(ids)
P=np.array([np.array(m[b],dtype=float)*8/1000.0 for b in ids])
role=sel['role'].values
MODE=sys.argv[1] if len(sys.argv)>1 else 'real'
G=float(sys.argv[2]) if len(sys.argv)>2 else 0.025
VEL=float(sys.argv[3]) if len(sys.argv)>3 else 0.5    # m/s

dt=0.1; T=4000.0; steps=int(T/dt); TAU=20.; TA=120.; BA=.5
# 每條邊的延遲（步數）
DEL=np.ones((N,N),dtype=int)
for j in range(N):
    for i in range(N):
        if W[j,i]!=0:
            if MODE=='real':
                dist=np.linalg.norm(P[i]-P[j])          # µm
                DEL[j,i]=max(1,int(round(dist/(VEL*1000)/dt)))
            else:
                DEL[j,i]=int(round(0.5/dt))             # 統一 0.5ms
mx=DEL[W!=0].max()
buf=np.zeros((mx+1,N))                                   # 環狀緩衝
V=np.random.default_rng(0).normal(0,.05,N); ad=np.zeros(N)
rng=np.random.default_rng(1); cmd=np.where(role=='CMD')[0]
rec=np.zeros((steps,N),dtype=np.float32)
pre_i,pre_j=np.nonzero(W.T)      # W[j,i] -> 用 (i,j)
for t in range(steps):
    inj=np.zeros(N)
    for i,j in zip(pre_i,pre_j):
        s=buf[(t-DEL[j,i])%(mx+1), i]
        if s: inj[j]+=W[j,i]*s
    drv=np.zeros(N); drv[cmd]=1.6
    # ★ 修正 dt 依賴：原本漏電項乘 dt、突觸項沒乘 -> 改 dt 會偷偷改變耦合強度，
    #   uniform 與 real 的比較就被 dt 汙染了。改成兩項都在同一個 dt 縮放裡。
    V += (dt/TAU)*(-V + inj*G/(0.5/TAU) + drv*20) - ad*dt/0.5 + rng.normal(0,.02*np.sqrt(dt/0.5),N)
    ad += dt/TA*(-ad)
    sp=(V>1.).astype(float); V*=(1-sp); ad+=BA*sp
    buf[t%(mx+1)]=sp; rec[t]=sp
burn=int(800/dt); R=rec[burn:]
k=np.ones(int(30/dt))/int(30/dt)
e1=np.where(role=='E1')[0]
x=np.convolve(R[:,e1].sum(1),k,'same')
def dom(z,dtms):
    z=z-z.mean()
    if z.std()<1e-9: return 0,0
    F=np.fft.rfft(z); fr=np.fft.rfftfreq(len(z),dtms/1000.)
    pw=np.abs(F)**2; pw[0]=0
    lo=np.searchsorted(fr,2.0); hi=np.searchsorted(fr,40.0)
    kk=lo+pw[lo:hi].argmax()
    return fr[kk], pw[max(1,kk-2):kk+3].sum()/pw[1:].sum()
f1,c1=dom(x,dt); f2,c2=dom(x[len(x)//2:],dt)
print(f"MODE={MODE:8s} G={G} VEL={VEL} m/s  最大延遲 {mx} 步 = {mx*dt:.2f}ms")
print(f"  E1 主頻 全段 {f1:.2f} Hz (集中度 {c1*100:.0f}%)   後半 {f2:.2f} Hz")
print(f"  {'穩定' if abs(f1-f2)/max(f1,1e-9)<0.25 else '漂移'}   E1 發火率 {R[:,e1].sum()/len(e1)/(len(R)*dt/1000):.1f} Hz")
