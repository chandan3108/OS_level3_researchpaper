from pathlib import Path
from collections import defaultdict
import csv,json,hashlib
import numpy as np
from analysis_utils import interval,write_csv

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'results/calibrated'
KEYS=('profile','cooling','overhead','pattern','scenario')
METRICS=('estimated_j_per_task','deadline_miss_pct','overhead_time_s','estimated_peak_c','p95_latency_ms','mode_switches')

def analyze(rows,keys=KEYS):
    groups=defaultdict(list)
    for r in rows:
        r=dict(r);r['seed']=int(r['seed'])
        for m in METRICS:r[m]=float(r[m])
        groups[tuple(r[k] for k in keys)].append(r)
    aggregates=[];paired=[];matched=0
    for key,group in sorted(groups.items()):
        controllers=defaultdict(dict)
        for r in group:
            assert r['seed'] not in controllers[r['controller']]
            controllers[r['controller']][r['seed']]=r
        assert set(controllers)=={'uncorrected','legacy_guard','calibrated_static','calibrated_feedback'}
        seeds=sorted(controllers['calibrated_static']);assert seeds==list(range(100,120))
        for seed in seeds:
            match=[d[seed] for d in controllers.values()]
            for field in ('task_sha256','estimate_sha256','calibration_sha256','calibration_gain','tasks','horizon_s','shared_config_sha256'):
                assert len({str(r[field]) for r in match})==1,(key,seed,field)
            assert all(float(r['completion_time_s'])<=40 and float(r['horizon_s'])==40 for r in match)
            matched+=1
        for controller,values in controllers.items():
            out=dict(zip(keys,key),controller=controller,n=20)
            for m in METRICS:
                out[m+'_mean']=float(np.mean([values[s][m] for s in seeds]))
            aggregates.append(out)
        a=controllers['calibrated_feedback']
        for baseline in ('calibrated_static','legacy_guard','uncorrected'):
            b=controllers[baseline];out=dict(zip(keys,key),target='calibrated_feedback',baseline=baseline,n=20)
            for m in METRICS:
                delta=[a[s][m]-b[s][m] for s in seeds]
                for label,value in zip(('mean','ci_low','ci_high','variation'),interval(delta)):
                    out[m+'_delta_'+label]=value
            wins=losses=zero_a=zero_b=0
            for s in seeds:
                de=a[s]['estimated_j_per_task']-b[s]['estimated_j_per_task']
                dm=a[s]['deadline_miss_pct']-b[s]['deadline_miss_pct']
                wins+=de<=1e-9 and dm<=1e-9 and (de< -1e-9 or dm< -1e-9)
                losses+=de>=-1e-9 and dm>=-1e-9 and (de>1e-9 or dm>1e-9)
                zero_a+=a[s]['deadline_miss_pct']==0;zero_b+=b[s]['deadline_miss_pct']==0
            out.update(joint_better=wins,joint_worse=losses,tradeoff_or_tie=20-wins-losses,
                       feedback_zero_miss_runs=zero_a,baseline_zero_miss_runs=zero_b,
                       calibration_gain_mean=float(np.mean([float(a[s]['calibration_gain']) for s in seeds])))
            paired.append(out)
    return aggregates,paired,matched

def main():
    rows=list(csv.DictReader((OUT/'runs.csv').open()))
    a,p,n=analyze(rows);assert len(rows)==6400 and n==1600
    write_csv(OUT/'aggregates.csv',a);write_csv(OUT/'paired.csv',p)
    sa,sp,sn=analyze(list(csv.DictReader((OUT/'sensitivity.csv').open())),keys=('e_power_factor','scenario'))
    write_csv(OUT/'sensitivity_paired.csv',sp)
    summary={'evaluations':len(rows),'matched_groups':n,'conditions':80,'seeds_per_condition':20,
       'sensitivity_evaluations':480,'primary_comparisons':80,'all_paired_contrasts':len(p),
       'analysis_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
       'analysis_plan_sha256':hashlib.sha256((ROOT/'revisions/2026-10-30/ANALYSIS_PLAN.md').read_bytes()).hexdigest(),
       'native_testing':'ON HOLD','physical_validation':False,'all_conditions_retained':True}
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    lines=['# Equal-history comparison: all primary conditions','',
       'Feedback minus calibrated static. Negative energy/miss differences favor feedback.',
       '20 paired seeds per condition. Variable differences have pointwise exploratory bootstrap intervals; constants are descriptive.',
       'All energy and temperature data are synthetic; native device testing is on hold.','',
       '| Profile | Cooling | Cost | Arrivals | Scenario | Δ energy J/task | Δ misses pp | Joint better/worse/other |',
       '|---|---|---|---|---|---:|---:|---|']
    for r in p:
        if r['baseline']!='calibrated_static':continue
        lines.append('| '+' | '.join(str(r[k]) for k in KEYS)+f" | {r['estimated_j_per_task_delta_mean']:+.6f} | {r['deadline_miss_pct_delta_mean']:+.3f} | {r['joint_better']}/{r['joint_worse']}/{r['tradeoff_or_tie']} |")
    (OUT/'RESULTS.md').write_text('\n'.join(lines)+'\n')
    print('Verified',n,'groups;',len(p),'contrasts; all 80 primary conditions retained.')
    for r in p:
        if (r['profile'],r['cooling'],r['overhead'],r['pattern'],r['baseline'])==('apple_inspired','ordinary','modeled_cost','bursty','calibrated_static'):
            print(r['scenario'],'ΔE',round(r['estimated_j_per_task_delta_mean'],6),'Δmiss',round(r['deadline_miss_pct_delta_mean'],3),'joint',r['joint_better'],r['joint_worse'],r['tradeoff_or_tie'])

if __name__=='__main__':main()
