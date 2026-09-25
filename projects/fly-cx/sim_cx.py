"""brian2 LIF 跑真 CX 接線，看 heading bump 會不會形成／持續／被轉動。"""
import numpy as np, pickle, sys
from brian2 import *
prefs.codegen.target='numpy'          # 不依賴 C 編譯器
seed(1); np.random.seed(1)

d=pickle.load(open('cx.pkl','rb')); A=d['A']; cx=d['cx']; N=len(cx)
fam=cx['fam'].values; theta=cx['theta'].values
is_epg=np.isin(fam,['EPG','EPGt']); is_pen=np.isin(fam,['PEN_a','PEN_b'])
side=cx['side'].values

eqs='''dv/dt = (-(v-El) + I + Iext)/tau : volt
       I : volt
       Iext : volt'''
G=NeuronGroup(N, eqs, threshold='v>-50*mV', reset='v=-70*mV',
              refractory=2*ms, method='euler')
G.namespace.update(El=-70*mV, tau=20*ms)
G.v=-70*mV

pre,post=np.nonzero(A)
w=A[pre,post]
W_SCALE=float(sys.argv[1]) if len(sys.argv)>1 else 0.011
PEN_DRIVE=float(sys.argv[2]) if len(sys.argv)>2 else 24.0
INH=float(sys.argv[3]) if len(sys.argv)>3 else 1.0
S=Synapses(G,G,'w_s : volt', on_pre='I_post += w_s')
S.connect(i=pre,j=post)
ww=w.copy(); ww[ww<0]*=INH          # 抑制獨立增益
S.w_s=ww*W_SCALE*mV
tau_I=30*ms
G.run_regularly('I = I*exp(-dt/tau_I)', dt=defaultclock.dt)
G.namespace.update(tau_I=tau_I)

M=SpikeMonitor(G)

def bump(angles,th0,amp):
    dth=np.angle(np.exp(1j*(angles-th0)))
    return amp*np.exp(-dth**2/(2*0.6**2))

# 1) 打一個 bump 進 EPG
th0=0.0
G.Iext = 0*mV
G.Iext[is_epg] = bump(theta[is_epg],th0,28)*mV
run(300*ms)
# 2) 撤掉外部輸入 —— 看環吸引子自己撐不撐住
G.Iext = 0*mV
run(400*ms)
# 3) 給 PEN 不對稱驅動 = 「向右轉」
G.Iext[is_pen & (side=='R')] = PEN_DRIVE*mV
run(400*ms)
G.Iext = 0*mV
run(200*ms)

# --- 線性讀出：EPG 族群向量解碼 heading
t=M.t/ms; i=M.i[:]
epg_idx=np.where(is_epg)[0]
def decode(t0,t1):
    m=(t>=t0)&(t<t1)&np.isin(i,epg_idx)
    if m.sum()<3: return None,m.sum()
    z=np.exp(1j*theta[i[m]]).sum()
    return np.angle(z), m.sum()

print(f"W_SCALE={W_SCALE} INH={INH}  總 spike={len(t)}")
print(f"{'視窗(ms)':>14} {'階段':<22} {'解碼 heading':>12} {'EPG spikes':>11}")
for (a,b,lab) in [(0,300,'1 有輸入 bump'),(300,700,'2 撤輸入(持續?)'),
                  (700,1100,'3 PEN-R 驅動(轉?)'),(1100,1300,'4 再撤輸入')]:
    h,c=decode(a,b)
    hs=f"{np.degrees(h):7.1f}°" if h is not None else "   --  "
    print(f"{a:5d}-{b:<5d} {lab:<22} {hs:>12} {c:>11}")

# 細分階段2/3 看 bump 有沒有移動
print("\n細看 bump 位置隨時間：")
for a in range(300,1300,100):
    h,c=decode(a,a+100)
    hs=f"{np.degrees(h):7.1f}°" if h is not None else "   --  "
    print(f"  {a:4d}-{a+100:<4d}  {hs}  (n={c})")
