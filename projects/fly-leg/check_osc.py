"""0.33Hz 剛好等於視窗長度的一個週期 -> 可能只是緩慢漂移被 FFT 讀成「一個循環」。
   跑長 5 倍，看它是不是真的在振盪。"""
import numpy as np, pickle, scipy.sparse as sp, sys
np.random.seed(0)
d=pickle.load(open('T1.pkl','rb')); W=d['W']; t1=d['t1']; mot=d['mot']; N=W.shape[0]
G=float(sys.argv[1]); SHUF=len(sys.argv)>2 and sys.argv[2]=='shuffle'
if SHUF:
    rng=np.random.default_rng(1); Wc=W.tocoo(); perm=rng.permutation(N)
    W=sp.csr_matrix((Wc.data,(perm[Wc.row],perm[Wc.col])),shape=(N,N))
dt,T,tau=1.0,20000.0,20.0      # 20 秒
steps=int(T/dt); r=np.zeros(N,dtype=np.float32)
drv=np.where(t1['superclass'].values=='vnc_intrinsic')[0]
drv=np.random.default_rng(2).choice(drv,400,replace=False)
rec=np.zeros((steps,len(mot)),dtype=np.float32)
for s in range(steps):
    I=np.zeros(N,dtype=np.float32); I[drv]=3.0
    r += (dt/tau)*(-r + np.maximum(W.dot(r)*G + I + 0.35,0))
    if not np.isfinite(r).all(): print("發散"); raise SystemExit
    rec[s]=r[mot]
burn=int(2000/dt); R=rec[burn:]
pop=R.mean(1)
print(f"G={G} shuffled={SHUF}  20 秒")
print(f"  族群平均活動：前 1s {pop[:1000].mean():.4f}  中段 {pop[8000:9000].mean():.4f}  末 1s {pop[-1000:].mean():.4f}")
# 後半段單獨看：真振盪的話後半還是會振
for lab,seg in [('全段',R),('後半',R[len(R)//2:])]:
    Z=seg-seg.mean(0); fs=1000.0/dt
    F=np.fft.rfft(Z,axis=0); fr=np.fft.rfftfreq(len(seg),1/fs)
    pw=(np.abs(F)**2).sum(1); pw[0]=0; k=pw.argmax()
    act=Z.std(0)>1e-6
    ph=np.angle(F[k][act]); z=np.abs(np.exp(1j*ph).mean()) if act.sum() else float('nan')
    h=np.histogram(np.degrees(ph)%360,bins=8,range=(0,360))[0] if act.sum() else np.zeros(8,int)
    print(f"  {lab}: 主頻 {fr[k]:.3f}Hz  集中度 {pw[max(1,k-2):k+3].sum()/pw[1:].sum()*100:.1f}%  相位R {z:.3f}  分佈 {h.tolist()}")
# 峰值計數：真振盪會有多個峰
from numpy import diff, sign
pk=((diff(sign(diff(pop)))<0).sum())
print(f"  族群訊號在 18 秒內的局部峰數: {pk}   (真 5Hz 振盪應該 ~90 個；1-2 個就是漂移)")
