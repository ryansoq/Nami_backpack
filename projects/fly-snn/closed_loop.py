"""閉環：脈衝 KC/MBON（帶突觸時間常數）+ 真實 CPG 腿 -> 在場地上找糖。
★ 事前判準：
  ① 訓練後閉環找糖次數 >> 未訓練
  ② tau_s=0（delta 突觸）應該比 tau_s=8 差 —— 把開環的發現帶到閉環驗證
  ③ KC 要真的稀疏（不是每步都 6 顆）
"""
import numpy as np, sys
rng=np.random.default_rng(0)
NS,NKC,NMB=8,40,2
DT=1.0; TAU_M=20.0; VTH=1.0; BETA=5.0
Wsk=(rng.random((NKC,NS))<0.35)*rng.random((NKC,NS))*2.2

# ---- 真實 CPG（MaleCNS 實測突觸數）
SYN={('I1','E1'):-617,('E1','E2'):455,('I2','E1'):-341,('I1','E2'):-210,
     ('E2','I2'):202,('E1','I2'):106,('E2','I1'):74,('I2','E2'):-45,
     ('E2','E1'):14,('E1','I1'):7}
ROLE=['E1','E2','I1','I2']; NL,NPL=6,4; NC=NL*NPL
Wc=np.zeros((NC,NC))
for L in range(NL):
    for (a,b),w in SYN.items():
        Wc[L*NPL+ROLE.index(b), L*NPL+ROLE.index(a)]=w
OFF=np.array([339,141,39,158,248,265])
KCOUP=0.60; GC=0.025; TA=120.; BA=.5

class Fly:
    def __init__(s,tau_s=8.0,sparse_th=26.0):
        s.tau_s=tau_s; s.sth=sparse_th
        s.kV=np.zeros(NKC); s.kI=np.zeros(NKC)
        s.mV=np.zeros(NMB); s.mI=np.zeros(NMB)
        s.ema=np.zeros(NMB)
        s.cV=np.zeros(NC); s.cad=np.zeros(NC); s.csp=np.zeros(NC)
        s.rate=np.zeros(NL)
        s.x=550.; s.y=280.; s.head=0.; s.kcN=0; s.kcSteps=0
    def sense(s,sx,sy):
        dx,dy=sx-s.x,sy-s.y
        bear=(np.degrees(np.arctan2(dy,dx))-s.head)%360
        dist=np.hypot(dx,dy); o=np.zeros(NS)
        for j in range(NS):
            d=abs(((bear-j*45+540)%360)-180)
            o[j]=max(0,np.exp(-d*d/(2*42*42))/(1+dist/400)+(rng.random()-0.5)*0.10)
        return o,bear,dist
    def kc(s,o):
        drive=Wsk@o
        if s.tau_s>0: s.kI += (-s.kI/s.tau_s + drive)*DT
        else: s.kI = drive
        s.kV += DT/TAU_M*(-s.kV + s.kI*3.0)
        sp=(s.kV>s.sth).astype(float)          # ★ 真閾值，不是強制 6 顆
        if sp.sum()>8:                          # APL 全域抑制的上限
            keep=np.argsort(s.kV)[-8:]; m=np.zeros(NKC); m[keep]=1; sp=sp*m
        s.kV=s.kV*(1-sp); s.kcN+=sp.sum(); s.kcSteps+=1
        return sp
    def mbon(s,kcsp,Wkm):
        drive=Wkm@kcsp
        if s.tau_s>0: s.mI += (-s.mI/s.tau_s + drive)*DT
        else: s.mI = drive
        s.mV += DT/TAU_M*(-s.mV + s.mI)
        sp=(s.mV>VTH).astype(float); s.mV=s.mV*(1-sp)
        s.ema += DT/30.0*(-s.ema + sp*(1000.0/DT)/50.0)   # 發火率的移動平均
        return np.tanh((s.ema[0]-s.ema[1])*0.8)
    def legs(s,turn):
        dL=1.6*(1-turn*0.45); dR=1.6*(1+turn*0.45)
        inj=Wc@s.csp
        for L in range(NL):
            i=L*NPL
            for M in range(NL):
                if M!=L and s.csp[M*NPL]: inj[i]+=KCOUP*600*np.cos(np.radians(OFF[L]-OFF[M]))
        drv=np.zeros(NC)
        for L in range(NL):
            sd=dL if L%2==0 else dR
            drv[L*NPL]=sd; drv[L*NPL+1]=sd
        s.cV += DT/TAU_M*(-s.cV) + inj*GC + drv*DT/TAU_M*20 - s.cad + rng.normal(0,.02,NC)
        s.cad += DT/TA*(-s.cad)
        sp=(s.cV>1).astype(float); s.cV*=(1-sp); s.cad+=BA*sp; s.csp=sp
        for L in range(NL): s.rate[L]=s.rate[L]*0.97+(sp[L*NPL]+sp[L*NPL+1])*0.03
        mr=max(0.02,s.rate.max()); stance=int((s.rate<0.5*mr).sum())
        adv = min(stance,3)*0.06 if stance>=3 else -0.015
        s.head=(s.head+(dR-dL)*0.55)%360
        r=np.radians(s.head); s.x+=np.cos(r)*adv; s.y+=np.sin(r)*adv
        s.x%=1100; s.y%=560
        return adv

def collect(n_ep=200,T=40,tau_s=8.0,th=26.0):
    """老師開車，錄下 (KC 脈衝序列, 老師轉向)"""
    data=[]
    for _ in range(n_ep):
        f=Fly(tau_s,th); sx,sy=80+rng.random()*940,80+rng.random()*400
        f.x,f.y=80+rng.random()*940,80+rng.random()*400; f.head=rng.random()*360
        seq=[]; tt=0
        for t in range(T):
            o,bear,dist=f.sense(sx,sy)
            err=((bear+540)%360)-180; tt=np.tanh(err/40)
            seq.append(f.kc(o)); f.mbon(seq[-1],np.zeros((NMB,NKC))); f.legs(tt)
        data.append((np.array(seq),tt))
    return data

def mb_fwd(seq,Wkm,tau_s,keep=False):
    T=len(seq); V=np.zeros(NMB); I=np.zeros(NMB)
    Vs=np.zeros((T,NMB)); S=np.zeros((T,NMB))
    for t in range(T):
        d=Wkm@seq[t]
        if tau_s>0: I += (-I/tau_s + d)*DT
        else: I=d
        V += DT/TAU_M*(-V+I); Vs[t]=V
        sp=(V>VTH).astype(float); S[t]=sp; V=V*(1-sp)
    c=S.sum(0); turn=np.tanh((c[0]-c[1])*0.25)
    return (turn,S,Vs) if keep else turn

def train(Wkm,data,iters=400,lr=0.03,tau_s=8.0):
    for it in range(iters):
        b=[data[i] for i in rng.choice(len(data),12,replace=False)]
        gW=np.zeros_like(Wkm)
        for seq,tt in b:
            turn,S,Vs=mb_fwd(seq,Wkm,tau_s,keep=True)
            e=turn-tt; dturn=2*e*(1-turn*turn)
            dcnt=np.array([dturn*0.25,-dturn*0.25])
            dV=np.zeros(NMB); dI=np.zeros(NMB)
            for t in range(len(seq)-1,-1,-1):
                sg=1.0/(1.0+BETA*np.abs(Vs[t]-VTH))**2
                dVt=dcnt*sg+dV
                dI_t=dVt*DT/TAU_M+dI
                gW+=np.outer(dI_t*(DT if tau_s>0 else 1.0),seq[t])
                dV=dVt*(1-DT/TAU_M)*(1-S[t]); dI=dI_t*(1-DT/tau_s) if tau_s>0 else 0.
        Wkm-=lr*gW/len(b)
    return Wkm

def closed_loop(Wkm,steps=60000,tau_s=8.0,th=26.0):
    f=Fly(tau_s,th); sx,sy=80+rng.random()*940,80+rng.random()*400
    eaten=0
    for t in range(steps):
        o,bear,dist=f.sense(sx,sy)
        turn=f.mbon(f.kc(o),Wkm)
        f.legs(turn)
        if np.hypot(sx-f.x,sy-f.y)<24:
            eaten+=1; sx,sy=80+rng.random()*940,80+rng.random()*400
            f.x,f.y=80+rng.random()*940,80+rng.random()*400; f.head=rng.random()*360
    return eaten, f.kcN/max(1,f.kcSteps)

if __name__=="__main__":
    TS=float(sys.argv[1]) if len(sys.argv)>1 else 8.0
    TH=float(sys.argv[2]) if len(sys.argv)>2 else 26.0
    data=collect(tau_s=TS,th=TH)
    W0=rng.normal(0.6,0.2,(NMB,NKC))
    e0,k0=closed_loop(W0.copy(),tau_s=TS,th=TH)
    W=train(W0.copy(),data,tau_s=TS)
    e1,k1=closed_loop(W,tau_s=TS,th=TH)
    print(f"tau_s={TS} 閾值={TH}  KC 每步活躍 {k1:.2f}/40   未訓練 {e0} 顆 -> 訓練後 {e1} 顆")
