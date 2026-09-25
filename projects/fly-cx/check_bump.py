import numpy as np, pickle
from brian2 import *
prefs.codegen.target='numpy'; seed(1); np.random.seed(1)
d=pickle.load(open('cx.pkl','rb')); A=d['A']; cx=d['cx']; N=len(cx)
fam=cx['fam'].values; theta=cx['theta'].values; side=cx['side'].values
is_epg=np.isin(fam,['EPG','EPGt']); is_pen=np.isin(fam,['PEN_a','PEN_b'])
eqs='''dv/dt=(-(v-El)+I+Iext)/tau : volt
       I : volt
       Iext : volt'''
G=NeuronGroup(N,eqs,threshold='v>-50*mV',reset='v=-70*mV',refractory=2*ms,method='euler')
G.namespace.update(El=-70*mV,tau=20*ms); G.v=-70*mV
pre,post=np.nonzero(A); w=A[pre,post].copy(); w[w<0]*=10.0
S=Synapses(G,G,'w_s : volt',on_pre='I_post += w_s'); S.connect(i=pre,j=post); S.w_s=w*0.08*mV
G.namespace.update(tau_I=30*ms); G.run_regularly('I = I*exp(-dt/tau_I)',dt=defaultclock.dt)
M=SpikeMonitor(G)
dth=np.angle(np.exp(1j*(theta-0.0)))
G.Iext=0*mV; G.Iext[is_epg]=(28*np.exp(-dth[is_epg]**2/(2*0.6**2)))*mV
run(300*ms); G.Iext=0*mV; run(400*ms)
t=M.t/ms; i=M.i[:]
epg=np.where(is_epg)[0]
m=(t>=400)&(t<700)&np.isin(i,epg)
print("=== 撤輸入後 400-700ms，EPG 各角度的 spike 分佈 ===")
bins=np.round(np.degrees(theta[epg])).astype(int)
tot={}
for b in sorted(set(bins)):
    cells=epg[bins==b]
    c=np.isin(i[m],cells).sum()
    tot[b]=c
mx=max(tot.values()) or 1
for b,c in sorted(tot.items()):
    print(f"  {b:4d}°  {'#'*int(40*c/mx):<40} {c}")
act=np.array(list(tot.values()),dtype=float)
print(f"\n最強/平均 = {act.max()/act.mean():.2f}   (1.0=完全均勻=飽和, 越大越集中)")
print(f"有 spike 的角度格: {(act>0).sum()}/{len(act)}")
