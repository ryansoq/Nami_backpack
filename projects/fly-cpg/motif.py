"""真實 CPG 基元：1 抑制 + 2 興奮（bioRxiv 2025.09 對六腳節律必要且充分）。
   實作成 half-center：兩顆興奮互相經由抑制顆壓制 + 發火後適應電流。
   先驗證「單一基元會不會自己振盪」，不會就不用談步態。"""
import numpy as np

def run_motif(T=1200, dt=1.0, drive=1.30, w_ei=1.0, w_ie=1.6, noise=0.05,
              tau=20.0, tau_a=140.0, b_adapt=0.40, seed=0, coupling=None,
              n_units=1, shuffle=False):
    rng=np.random.default_rng(seed)
    # 每個 unit: [E1, E2, I]
    U=n_units; N=U*3
    E1=np.arange(U)*3; E2=E1+1; I=E1+2
    W=np.zeros((N,N))
    for u in range(U):
        e1,e2,i=3*u,3*u+1,3*u+2
        W[i,e1]=w_ei; W[i,e2]=w_ei          # 兩顆興奮都驅動抑制顆
        W[e1,i]=-w_ie; W[e2,i]=-w_ie        # 抑制顆壓制兩顆
        W[e2,e1]=-0.0; W[e1,e2]=-0.0
    # half-center 要的是「互相」壓制：讓 E1 經 I 壓 E2，用非對稱延遲實現
    # 這裡用直接交互抑制近似（生物上由 I 中介）
    for u in range(U):
        e1,e2=3*u,3*u+1
        W[e2,e1]=-1.10; W[e1,e2]=-1.10
    if coupling is not None:
        for (a,bb,w) in coupling:
            W[3*bb, 3*a]   += w             # unit a 的 E1 -> unit b 的 E1
            W[3*bb+1,3*a+1]+= w
    if shuffle:
        r=np.random.default_rng(7); nz=np.argwhere(W!=0); vals=W[W!=0]
        Wn=np.zeros_like(W); idx=r.permutation(len(vals))
        flat=r.choice(N*N,len(vals),replace=False)
        Wn.flat[flat]=vals[idx]; W=Wn

    steps=int(T/dt)
    # ★ 對稱是不穩定平衡：完全相同的初始值會讓兩顆興奮永遠同步。
    #   真神經元有雜訊，加一點點就會自己挑一個相位（對稱破壞）。
    V=rng.normal(0,0.15,N); a=np.zeros(N); rec=np.zeros((steps,N))
    NOISE=float(noise)
    Vr=0.0; VTH=1.0
    for t in range(steps):
        s_prev=rec[t-1] if t>0 else np.zeros(N)
        V += dt/tau*(Vr-V) + W@s_prev + drive - a + rng.normal(0,NOISE,N)
        a += dt/tau_a*(-a)
        sp=(V>VTH).astype(float)
        V=V*(1-sp); a+=b_adapt*sp
        rec[t]=sp
    return rec, (E1,E2,I)

if __name__=="__main__":
    rec,(E1,E2,I)=run_motif()
    dt=1.0
    def rate(ix,win=40):
        x=rec[:,ix].sum(1)
        k=np.ones(win)/win
        return np.convolve(x,k,mode='same')
    r1,r2=rate(E1),rate(E2)
    print("=== 單一基元 1 抑制 + 2 興奮 ===")
    print(f"  E1 總 spike {rec[:,E1].sum():.0f}   E2 {rec[:,E2].sum():.0f}   I {rec[:,I].sum():.0f}")
    # 主頻與反相程度
    z1=r1-r1.mean(); z2=r2-r2.mean()
    F=np.fft.rfft(z1); fr=np.fft.rfftfreq(len(z1),dt/1000.0)
    pw=np.abs(F)**2; pw[0]=0; k=pw.argmax()
    corr=np.corrcoef(z1,z2)[0,1]
    print(f"  主頻 {fr[k]:.2f} Hz   集中度 {pw[max(1,k-2):k+3].sum()/pw[1:].sum()*100:.1f}%")
    print(f"  ★ E1 與 E2 的相關 {corr:+.3f}   (-1 = 完美反相 = half-center 成立)")
    # 峰數
    d=np.diff(np.sign(np.diff(z1)))
    print(f"  E1 訊號峰數 {(d<0).sum()}  (1.2 秒內；真振盪應有數個)")
