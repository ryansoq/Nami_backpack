"""更像 LIF 的版本 + 可訓練：
   ① 突觸時間常數（指數衰減，不再是 delta 突觸）
   ② KC 與 MBON 都是真的 LIF（會發火、會重設）
   ③ 用 surrogate gradient + 截斷 BPTT 訓練 MBON 權重去模仿老師
      （做法沿用 fly-self-driving：行為克隆，離線用錄下來的老師軌跡）
★ 事前判準：
   ① 訓練後的模仿誤差要明顯低於未訓練
   ② 閉環放回去找糖，要贏過未訓練
   ③ 把突觸時間常數設成 0（退回 delta）結果應該不同 -> 證明它有影響
"""
import numpy as np
rng=np.random.default_rng(0)
NS,NKC,NMB=8,40,2
DT=1.0
TAU_M=20.0          # 膜時間常數
TAU_S=8.0           # ★ 突觸時間常數（新）
VTH=1.0
BETA=5.0            # surrogate 斜度

Wsk=(rng.random((NKC,NS))<0.35)*rng.random((NKC,NS))*2.2

def kc_spikes(s_seq, tau_s=TAU_S):
    """感覺序列 -> KC 脈衝序列。KC 是 LIF，輸入經過突觸濾波，
       再用前 6 名的 winner-take-all（近似真蒼蠅的 APL 全域抑制）。"""
    T=len(s_seq); V=np.zeros(NKC); I=np.zeros(NKC); out=np.zeros((T,NKC))
    for t in range(T):
        drive=Wsk@s_seq[t]
        I += (-I/tau_s + drive)*DT/1.0 if tau_s>0 else 0
        cur = I if tau_s>0 else drive
        V += DT/TAU_M*(-V + cur*3.0)
        # WTA：只讓最強的 6 顆有機會發火（APL 抑制的簡化）
        thr=np.sort(V)[-6] if NKC>6 else -1e9
        sp=((V>=thr)&(V>VTH*0.35)).astype(float)
        out[t]=sp; V=V*(1-sp)
    return out

def mbon_forward(kc_seq, Wkm, tau_s=TAU_S, keep=False):
    T=len(kc_seq); V=np.zeros(NMB); I=np.zeros(NMB)
    Vs=np.zeros((T,NMB)); Is=np.zeros((T,NMB)); S=np.zeros((T,NMB))
    for t in range(T):
        drive=Wkm@kc_seq[t]
        if tau_s>0: I += (-I/tau_s + drive)*DT
        else:       I = drive
        V += DT/TAU_M*(-V + I)
        Vs[t]=V; Is[t]=I
        sp=(V>VTH).astype(float); S[t]=sp; V=V*(1-sp)
    cnt=S.sum(0)
    turn=np.tanh((cnt[0]-cnt[1])*0.25)
    return (turn,cnt,S,Vs,kc_seq) if keep else turn

def train(Wkm, batch, lr=0.02, tau_s=TAU_S):
    """截斷 BPTT + surrogate gradient。batch = [(kc_seq, teacher_turn)]"""
    gW=np.zeros_like(Wkm); loss=0.0
    for kc_seq,tt in batch:
        turn,cnt,S,Vs,_=mbon_forward(kc_seq,Wkm,tau_s,keep=True)
        e=turn-tt; loss+=e*e
        dturn=2*e*(1-turn*turn)
        dcnt=np.array([dturn*0.25, -dturn*0.25])
        T=len(kc_seq); dV=np.zeros(NMB); dI=np.zeros(NMB)
        for t in range(T-1,-1,-1):
            sg=1.0/(1.0+BETA*np.abs(Vs[t]-VTH))**2      # surrogate 導數
            dVt=dcnt*sg + dV
            dI_t = dVt*DT/TAU_M + dI
            gW += np.outer(dI_t*(DT if tau_s>0 else 1.0), kc_seq[t])
            dV = dVt*(1-DT/TAU_M)*(1-S[t])
            dI = dI_t*(1-DT/tau_s) if tau_s>0 else 0.0
    n=max(1,len(batch))
    Wkm -= lr*gW/n
    return loss/n

def make_episode(T=40, tau_s=TAU_S):
    """隨機一個「糖在某個方位」的片段，老師答案 = tanh(方位/40)"""
    bear=rng.random()*360
    s_seq=np.zeros((T,NS))
    for t in range(T):
        for j in range(NS):
            c=j*45; d=abs(((bear-c+540)%360)-180)
            s_seq[t,j]=max(0,np.exp(-d*d/(2*42*42))+(rng.random()-0.5)*0.12)
    err=((bear+540)%360)-180
    return kc_spikes(s_seq,tau_s), np.tanh(err/40)

if __name__=="__main__":
    import sys
    TS=float(sys.argv[1]) if len(sys.argv)>1 else TAU_S
    Wkm=rng.normal(0.6,0.2,(NMB,NKC))
    eps=[make_episode(tau_s=TS) for _ in range(240)]
    def evaluate(W):
        return np.mean([abs(mbon_forward(k,W,TS)-t) for k,t in eps[:80]])
    print(f"tau_s={TS}  訓練前模仿誤差 {evaluate(Wkm):.4f}")
    for it in range(300):
        b=[eps[i] for i in rng.choice(len(eps),12,replace=False)]
        L=train(Wkm,b,lr=0.03,tau_s=TS)
    print(f"           訓練後模仿誤差 {evaluate(Wkm):.4f}   最後 loss {L:.4f}")
    kc,_=eps[0]
    print(f"  KC 平均發火率 {kc.mean()*1000/DT:.1f} Hz   每步活躍 {kc.sum(1).mean():.1f} 顆")
