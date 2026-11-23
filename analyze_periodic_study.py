import csv,json,hashlib,math
from collections import defaultdict
from pathlib import Path
import numpy as np
from analysis_utils import interval,write_csv
from periodic_study import CONTROLLERS

ROOT=Path(__file__).resolve().parent;OUT=ROOT/'results/periodic'
KEYS=('profile','cooling','overhead','pattern','scenario')
METRICS=('estimated_j_per_task','deadline_miss_pct','overhead_time_s','estimated_peak_c','p95_latency_ms','mode_switches')

def directional_test(values,tolerance=1e-9):
    negative=sum(v < -tolerance for v in values)
    positive=sum(v > tolerance for v in values)
    n=negative+positive
    p=sum(math.comb(n,k) for k in range(negative,n+1))/2**n if n else 1.
    return dict(negative_n=negative,positive_n=positive,tied_n=len(values)-n,nonzero_n=n,sign_p=p)

def holm_adjust(pvalues):
    order=sorted(range(len(pvalues)),key=lambda i:pvalues[i]);result=[0.]*len(order);running=0.
    for rank,i in enumerate(order):
        running=max(running,min(1.,(len(order)-rank)*pvalues[i]));result[i]=running
    return result

def contrast(a,b,meta):
    seeds=sorted(a);assert seeds==sorted(b)
    out=dict(meta,n=len(seeds))
    for metric in METRICS:
        differences=[float(a[s][metric])-float(b[s][metric]) for s in seeds]
        for label,value in zip(('mean','ci_low','ci_high','variation'),interval(differences)):
            out[metric+'_delta_'+label]=value
    wins=losses=strict=zero_a=zero_b=0
    for s in seeds:
        de=float(a[s]['estimated_j_per_task'])-float(b[s]['estimated_j_per_task'])
        dm=float(a[s]['deadline_miss_pct'])-float(b[s]['deadline_miss_pct'])
        wins+=de<=1e-9 and dm<=1e-9 and (de< -1e-9 or dm< -1e-9)
        losses+=de>=-1e-9 and dm>=-1e-9 and (de>1e-9 or dm>1e-9)
        strict+=de< -1e-9 and dm<=1e-9
        zero_a+=float(a[s]['deadline_miss_pct'])==0
        zero_b+=float(b[s]['deadline_miss_pct'])==0
    out.update(joint_better=wins,joint_worse=losses,tradeoff_or_tie=len(seeds)-wins-losses,
               strict_energy_joint_better=strict,feedback_zero_miss_runs=zero_a,baseline_zero_miss_runs=zero_b)
    return out

def analyze(rows):
    grouped=defaultdict(lambda:defaultdict(dict))
    for r in rows:
        key=tuple(r[k] for k in KEYS);seed=int(r['seed'])
        assert seed not in grouped[key][r['controller']]
        grouped[key][r['controller']][seed]=r
    agg=[];paired=[];family=[]
    for key,controllers in sorted(grouped.items()):
        assert set(controllers)==set(CONTROLLERS)
        seeds=list(range(200,220));meta=dict(zip(KEYS,key))
        for c,d in controllers.items():assert sorted(d)==seeds
        for seed in seeds:
            match=[d[seed] for d in controllers.values()]
            for field in ('task_sha256','estimate_sha256','calibration_sha256','calibration_gain','tasks','horizon_s','shared_config_sha256'):
                assert len({str(r[field]) for r in match})==1,(key,seed,field)
            assert all(float(r['horizon_s'])==40 and float(r['completion_time_s'])<=40 for r in match)
        for c,d in controllers.items():
            record=dict(meta,controller=c,n=20)
            for m in METRICS:record[m+'_mean']=float(np.mean([float(d[s][m]) for s in seeds]))
            record['zero_miss_runs']=sum(float(d[s]['deadline_miss_pct'])==0 for s in seeds)
            record['correction_updates_mean']=float(np.mean([float(d[s]['correction_updates']) for s in seeds]))
            agg.append(record)
        a=controllers['calibrated_feedback']
        for baseline in CONTROLLERS:
            if baseline=='calibrated_feedback':continue
            b=controllers[baseline]
            paired.append(contrast(a,b,dict(meta,target='calibrated_feedback',baseline=baseline)))
            if baseline=='periodic_20' and meta['cooling']=='ordinary' and meta['overhead']=='modeled_cost' and meta['pattern']=='bursty' and meta['scenario'] in ('high_to_low','accurate_to_low'):
                for metric in ('estimated_j_per_task','deadline_miss_pct'):
                    values=[float(a[s][metric])-float(b[s][metric]) for s in seeds]
                    family.append(dict(meta,target='calibrated_feedback',baseline=baseline,endpoint=metric,
                                       **directional_test(values)))
    if family:
        assert len(family)==8
        for row,p in zip(family,holm_adjust([r['sign_p'] for r in family])):
            row['holm_p']=p;row['reject_at_05']=p<.05
    return agg,paired,family

def main():
    rows=list(csv.DictReader((OUT/'runs.csv').open()))
    agg,pairs,family=analyze(rows);assert len(rows)==5600 and len(pairs)==240 and len(family)==8
    write_csv(OUT/'aggregates.csv',agg);write_csv(OUT/'paired.csv',pairs);write_csv(OUT/'primary_family.csv',family)
    za,zp,zf=analyze(list(csv.DictReader((OUT/'zero_cost.csv').open())))
    assert not zf;write_csv(OUT/'zero_cost_paired.csv',zp)
    extra=list(csv.DictReader((OUT/'equal_completion_cost.csv').open()));equal=[]
    for profile in ('generic','apple_inspired'):
        for scenario in ('high_to_low','accurate_to_low'):
            a={int(r['seed']):r for r in rows if r['profile']==profile and r['scenario']==scenario and r['pattern']=='bursty' and r['cooling']=='ordinary' and r['controller']=='calibrated_feedback'}
            b={int(r['seed']):r for r in extra if r['profile']==profile and r['scenario']==scenario}
            for s in a:
                for field in ('task_sha256','estimate_sha256','calibration_sha256'):
                    assert a[s][field]==b[s][field]
            equal.append(contrast(a,b,dict(profile=profile,scenario=scenario,target='calibrated_feedback',baseline='periodic_20',cost_sensitivity='equal_completion')))
    write_csv(OUT/'equal_completion_paired.csv',equal)
    summary=dict(main_evaluations=len(rows),conditions=40,matched_groups=800,seeds_per_condition=20,
                 exploratory_contrasts=len(pairs),primary_family_endpoints=8,
                 holm_rejections=sum(r['reject_at_05'] for r in family),zero_cost_evaluations=560,
                 equal_completion_evaluations=80,physical_validation=False,native_testing='ON HOLD',
                 analysis_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                 plan_sha256=hashlib.sha256((ROOT/'revisions/2026-10-31/EXPERIMENT_AND_ANALYSIS_PLAN.md').read_bytes()).hexdigest())
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    lines=['# Fresh-seed periodic/windowed recalibration follow-up','',
           'EWMA minus each comparator; negative energy and miss differences favor EWMA.',
           'All results synthetic. 20 paired streams per condition. Pointwise intervals are exploratory.',
           'The fixed eight-test Holm family concerns directional consistency among non-tied pairs, not mean effects or noninferiority.','',
           '| Profile | Cooling | Arrivals | Scenario | Baseline | Delta J/task | Delta miss pp | Joint better/worse/other | Zero-miss EWMA/baseline |',
           '|---|---|---|---|---|---:|---:|---|---|']
    for r in pairs:
        lines.append('| '+' | '.join(str(r[k]) for k in ('profile','cooling','pattern','scenario','baseline'))+
                     f" | {r['estimated_j_per_task_delta_mean']:+.6f} | {r['deadline_miss_pct_delta_mean']:+.3f} | {r['joint_better']}/{r['joint_worse']}/{r['tradeoff_or_tie']} | {r['feedback_zero_miss_runs']}/{r['baseline_zero_miss_runs']} |")
    (OUT/'RESULTS.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(summary,indent=2))
    for r in pairs:
        if r['profile']=='apple_inspired' and r['cooling']=='ordinary' and r['pattern']=='bursty' and r['baseline']=='periodic_20':
            print(r['scenario'],'E',round(r['estimated_j_per_task_delta_mean'],7),'miss',round(r['deadline_miss_pct_delta_mean'],4),'joint',r['joint_better'],r['joint_worse'],r['tradeoff_or_tie'])

if __name__=='__main__':main()
