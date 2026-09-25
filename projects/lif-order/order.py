"""200 顆 LIF，學「誰先響」。手寫 surrogate gradient + BPTT，只用 numpy。

★ 事前判準：
  ① LIF 正確率 > 90%
  ② ANN（時間加總）≈ 50%   <- 數學保證：兩類加總後完全相同
  ③ τ 調大到不漏電 -> LIF 掉回 50%  <- 證明做事的是漏電項
"""
import numpy as np, sys
rng=np.random.default_rng(0)
T, H, DT = 60, 200, 1.0          # 60 ms, 200 hidden, dt=1ms
TAU  = float(sys.argv[1]) if len(sys.argv)>1 else 20.0
GAP  = 5                          # 兩事件間隔 5ms
BETA = 5.0                        # surrogate 斜度

def make(n):
    """回傳 x:(n,T,2), y:(n,)  兩類 spike 總數完全相同，只有順序不同。"""
    x=np.zeros((n,T,2),dtype=np.float64); y=rng.integers(0,2,n)
    t0=rng.integers(12,28,n)                     # 抖動起始時間，避免死記
    for i in range(n):
        a,b=(t0[i],t0[i]+GAP) if y[i]==0 else (t0[i]+GAP,t0[i])
        x[i,a,0]=1.0; x[i,b,1]=1.0
    return x,y

def fwd(x,Win,Wout,bout,tau,keep=False):
    n=x.shape[0]; decay=1.0-DT/tau
    V=np.zeros((n,H)); S=[]; Vs=[]
    for t in range(T):
        V=V*decay + x[:,t,:]@Win
        s=(V>1.0).astype(np.float64)
        Vs.append(V.copy()); S.append(s)
        V=V*(1.0-s)                              # reset（梯度 detach）
    S=np.stack(S,1); Vs=np.stack(Vs,1)           # (n,T,H)
    c=S.sum(1)                                   # rate readout
    logits=c@Wout+bout
    return (logits,c,S,Vs) if keep else logits

def softmax_ce(logits,y):
    z=logits-logits.max(1,keepdims=True); e=np.exp(z); p=e/e.sum(1,keepdims=True)
    n=len(y); loss=-np.log(p[np.arange(n),y]+1e-12).mean()
    d=p.copy(); d[np.arange(n),y]-=1.0; d/=n
    return loss,d,p

def train_lif(tau,epochs=300,n=600,lr=0.05,seed=1):
    r=np.random.default_rng(seed)
    Win=r.normal(0,0.8,(2,H)); Wout=r.normal(0,0.3,(H,2)); bout=np.zeros(2)
    xtr,ytr=make(n); xte,yte=make(400)
    decay=1.0-DT/tau
    for ep in range(epochs):
        logits,c,S,Vs=fwd(xtr,Win,Wout,bout,tau,keep=True)
        loss,dlog,_=softmax_ce(logits,ytr)
        gWout=c.T@dlog; gbout=dlog.sum(0); dc=dlog@Wout.T          # (n,H)
        gWin=np.zeros_like(Win); dV=np.zeros((n,H))
        for t in range(T-1,-1,-1):
            sg=1.0/(1.0+BETA*np.abs(Vs[:,t]-1.0))**2               # surrogate'
            dVt=dc*sg + dV
            gWin+=xtr[:,t,:].T@dVt
            dV=dVt*decay*(1.0-S[:,t])
        for g,p in ((gWin,Win),(gWout,Wout),(gbout,bout)):
            p-=lr*g/np.maximum(1e-8,np.abs(g).max())
    acc=(fwd(xte,Win,Wout,bout,tau).argmax(1)==yte).mean()
    return acc,loss

def train_ann(n=600,epochs=600,lr=0.2,seed=1):
    """對照：把輸入沿時間加總（ANN 看到的就是這個），再做線性分類。"""
    r=np.random.default_rng(seed)
    xtr,ytr=make(n); xte,yte=make(400)
    a=xtr.sum(1); b=xte.sum(1)                                     # (n,2) 全是 [1,1]
    W=r.normal(0,0.3,(2,2)); bb=np.zeros(2)
    for ep in range(epochs):
        loss,d,_=softmax_ce(a@W+bb,ytr)
        W-=lr*(a.T@d); bb-=lr*d.sum(0)
    return ((b@W+bb).argmax(1)==yte).mean(), a[:4]

if __name__=="__main__":
    print(f"=== 資料檢查（這是 ② 的數學保證）===")
    x,y=make(6)
    print("  每筆沿時間加總後的輸入向量：")
    for i in range(6): print(f"    y={y[i]}  sum over time = {x[i].sum(0)}")
    accA,ex=train_ann()
    print(f"\n② ANN（時間加總）正確率 {accA*100:.1f}%")
    print(f"\n① LIF  tau={TAU}ms")
    acc,loss=train_lif(TAU)
    print(f"   正確率 {acc*100:.1f}%   最終 loss {loss:.4f}")
