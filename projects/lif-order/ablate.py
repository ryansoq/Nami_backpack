"""判準③失敗 -> 漏電不是機制。用消融法找真正的機制。

假說 B：關鍵是「非線性在時間軸上「每一步」都作用一次」。
  ANN  logits = f( Σ_t x )    先加總，再過一次非線性
  LIF  count  = Σ_t f( V_t )  每一步都過一次非線性
若假說 B 對，把閾值拿掉（純線性積分）就該掉回 50%。
"""
import numpy as np
exec(open('order.py').read().split('if __name__')[0])

def fwd_lin(x,Win,wout,bout,tau):
    """沒有閾值、沒有發火、沒有重設 —— 純線性積分，最後讀 V。"""
    n=x.shape[0]; decay=1.0-DT/tau; V=np.zeros((n,H))
    for t in range(T): V=V*decay + x[:,t,:]@Win
    return V@wout+bout, V

def train_lin(tau=20.0,epochs=600,n=600,lr=0.1,seed=1):
    r=np.random.default_rng(seed)
    Win=r.normal(0,0.8,(2,H)); wout=r.normal(0,0.3,(H,2)); bout=np.zeros(2)
    xtr,ytr=make(n); xte,yte=make(400); decay=1.0-DT/tau
    for ep in range(epochs):
        logits,V=fwd_lin(xtr,Win,wout,bout,tau)
        loss,d,_=softmax_ce(logits,ytr)
        gw=V.T@d; gb=d.sum(0); dV=d@wout.T
        gWin=np.zeros_like(Win); acc=dV.copy()
        for t in range(T-1,-1,-1):
            gWin+=xtr[:,t,:].T@acc; acc=acc*decay
        for g,p in ((gWin,Win),(gw,wout),(gb,bout)):
            p-=lr*g/np.maximum(1e-8,np.abs(g).max())
    a,_=fwd_lin(xte,Win,wout,bout,tau)
    return (a.argmax(1)==yte).mean()

print("=== 消融實驗：機制到底是什麼 ===")
print(f"  ① 完整 LIF（漏電+閾值+重設）tau=20      {train_lif(20.0)[0]*100:5.1f}%")
print(f"  ② 無漏電 LIF（tau=10000，仍有閾值）     {train_lif(10000.0)[0]*100:5.1f}%")
print(f"  ③ 有漏電但無閾值（純線性積分）tau=20     {train_lin(20.0)*100:5.1f}%")
print(f"  ④ 無漏電也無閾值（＝ANN）tau=10000       {train_lin(10000.0)*100:5.1f}%")
