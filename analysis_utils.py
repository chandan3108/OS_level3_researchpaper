import csv
import numpy as np

def interval(values):
    a=np.asarray(values,dtype=float);mean=float(a.mean())
    if np.ptp(a)<=1e-12:return mean,None,None,'constant'
    rng=np.random.default_rng(20261029)
    samples=a[rng.integers(len(a),size=(5000,len(a)))].mean(axis=1)
    return mean,float(np.quantile(samples,.025)),float(np.quantile(samples,.975)),'variable'

def write_csv(path,rows):
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

