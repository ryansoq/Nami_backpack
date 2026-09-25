import numpy as np, pickle, json
d=pickle.load(open('real_cpg.pkl','rb')); W0=d['W']; sel=d['sel']
N=len(sel); role=sel['role'].values; seg=sel['seg'].values; side=sel['side'].values
def run(G,T=2000.0,shuf=False,seed=0):
    W=W0.copy()
    if shuf:
        r=np.random.default_rng(3); nz=W[W!=0]; Wn=np.zeros_like(W)
        Wn.flat[r.choice(N*N,len(nz),replace=False)]=r.permutation(nz); W=Wn
    dt=0.5; steps=int(T/dt); TAU=20.;TA=120.;BA=.5
    V=np.random.default_rng(seed).normal(0,.05,N); ad=np.zeros(N)
    rec=np.zeros((steps,N),np.float32); rng=np.random.default_rng(seed+1)
    cmd=np.where(role=='CMD')[0]
    for t in range(steps):
        sp_=rec[t-1] if t else np.zeros(N)
        drv=np.zeros(N); drv[cmd]=1.6
        V+=dt/TAU*(-V)+(W@sp_)*G+drv*dt/TAU*20-ad+rng.normal(0,.02,N)
        ad+=dt/TA*(-ad); s=(V>1.).astype(np.float32); V*=(1-s); ad+=BA*s; rec[t]=s
    return rec,dt
def analyse(rec,dt,burn=800):
    R=rec[burn:]; k=np.ones(60)/60
    def rt(ix): return np.convolve(R[:,ix].sum(1),k,'same')
    out={}
    e1=np.where(role=='E1')[0]; x=rt(e1); z=x-x.mean()
    F=np.fft.rfft(z); fr=np.fft.rfftfreq(len(z),dt/1000.); pw=np.abs(F)**2; pw[0]=0
    kk=pw.argmax(); out['f']=float(fr[kk]); out['conc']=float(pw[max(1,kk-2):kk+3].sum()/pw[1:].sum())
    zh=z[len(z)//2:]; Fh=np.fft.rfft(zh); frh=np.fft.rfftfreq(len(zh),dt/1000.); pwh=np.abs(Fh)**2; pwh[0]=0
    out['f_half']=float(frh[pwh.argmax()])
    out['rates']={r: float(R[:,role==r].sum()/max(1,(role==r).sum())/(len(R)*dt/1000)) for r in ('CMD','E1','E2','I1','I2')}
    ph={}
    for s in ('T1','T2','T3'):
        for sd in ('L','R'):
            ix=np.where((role=='E1')&(seg==s)&(side==sd))[0]
            if not len(ix): continue
            xx=rt(ix); zz=xx-xx.mean()
            if zz.std()<1e-9: ph[s+sd]=None; continue
            Fz=np.fft.rfft(zz); pz=np.abs(Fz)**2; pz[0]=0
            ph[s+sd]=float(np.degrees(np.angle(Fz[pz.argmax()]))%360)
    out['phases']=ph
    out['trace']=[round(float(v),3) for v in x[::8][:220]]
    # raster（抽樣）
    idxs=[int(i) for i in np.where(role!='CMD')[0]]
    out['raster']=[[int(t) for t in np.where(R[:,i])[0][:120]] for i in idxs]
    out['raster_labels']=[f"{role[i]} {seg[i]}{side[i][:1]}" for i in idxs]
    out['nT']=int(len(R))
    return out

data={'sweep':[], 'circuit':[], 'best':None, 'shuf':None}
for G in (0.002,0.004,0.008,0.015,0.025,0.04,0.07):
    rec,dt=run(G); a=analyse(rec,dt)
    data['sweep'].append({'G':G,'f':a['f'],'f_half':a['f_half'],'conc':a['conc'],'E1':a['rates']['E1']})
    print(f"  G={G:<6} f={a['f']:.2f}/{a['f_half']:.2f} conc={a['conc']*100:.0f}% E1={a['rates']['E1']:.1f}Hz")
rec,dt=run(0.025); data['best']=analyse(rec,dt); data['best']['G']=0.025
rec,dt=run(0.025,shuf=True); data['shuf']=analyse(rec,dt); data['shuf']['G']=0.025
# 電路邊（給圖用）：只取同一節同一側的代表性連線
import collections
agg=collections.defaultdict(list)
for i in range(N):
    for j in range(N):
        if W0[j,i]!=0 and role[i]!='CMD' and role[j]!='CMD' and seg[i]==seg[j] and side[i]==side[j]:
            agg[(role[i],role[j])].append(abs(W0[j,i]))
for (a_,b_),v in sorted(agg.items(),key=lambda x:-np.mean(x[1])):
    data['circuit'].append({'pre':a_,'post':b_,'syn':int(np.mean(v)),'sign':1 if a_ in ('E1','E2') else -1})
print("\n=== 電路（同節同側平均突觸數）===")
for c in data['circuit']: print(f"  {c['pre']} -> {c['post']:3s} {c['syn']:5d} {'+' if c['sign']>0 else '-'}")
json.dump(data,open('cpg_data.json','w'),separators=(',',':'))
import os; print("\ncpg_data.json",os.path.getsize('cpg_data.json')//1024,"KB")
