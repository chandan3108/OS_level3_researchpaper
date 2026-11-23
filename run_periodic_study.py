import csv, hashlib, json, os, platform, time
from dataclasses import asdict, replace
from pathlib import Path
from periodic_study import Settings, CONTROLLERS, simulate
from run_calibrated_study import calibration, workload, config, fingerprint, SCENARIOS

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'results/periodic'
SEEDS=tuple(range(200,220))

def execute(seed,pattern,scenario,profile,cooling='ordinary',cost='modeled_cost',
            controllers=CONTROLLERS,equal_completion_cost=False):
    tasks,estimates=workload(seed,pattern,scenario)
    gain,history=calibration(seed,scenario)
    base=Settings(**asdict(config(profile,cooling,cost,gain)))
    if cost=='zero_cost':
        base=replace(base,completion_observation_cost_s=0.,recalibration_application_cost_s=0.)
    elif equal_completion_cost:
        base=replace(base,completion_observation_cost_s=.00005,recalibration_application_cost_s=0.)
    common=dict(seed=seed,pattern=pattern,scenario=scenario,profile=profile,cooling=cooling,
        overhead=cost,cost_sensitivity='equal_completion' if equal_completion_cost else 'default',
        calibration_gain=gain,calibration_count=len(history),calibration_sha256=fingerprint(history),
        task_sha256=fingerprint([asdict(t) for t in tasks]),estimate_sha256=fingerprint(estimates),
        shared_config_sha256=fingerprint(asdict(base)),e_power_factor=base.e_power_factor)
    rows=[]
    for controller in controllers:
        result,_=simulate(controller,tasks,base,estimates,history)
        result.update(common);rows.append(result)
    return rows

def write_rows(path,rows):
    with path.open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)

def main():
    OUT.mkdir(exist_ok=True)
    try:os.nice(10)
    except (AttributeError,OSError):pass
    sources=('periodic_study.py','run_periodic_study.py','calibrated_study.py',
             'run_calibrated_study.py','study.py','revisions/2026-10-31/EXPERIMENT_AND_ANALYSIS_PLAN.md')
    meta={'seeds':SEEDS,'controllers':CONTROLLERS,'worker_count':1,'python':platform.python_version(),
          'physical_validation':False,'native_testing':'ON HOLD','apple_model_calibrated':False,
          'primary_baseline':'periodic_20','primary_family_endpoints':8,
          'source_sha256':{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in sources}}
    (OUT/'settings.json').write_text(json.dumps(meta,indent=2)+'\n')
    start=time.monotonic();rows=[];groups=0
    for profile in ('generic','apple_inspired'):
        for cooling in ('ordinary','restricted'):
            for pattern in ('bursty','poisson'):
                for scenario in SCENARIOS:
                    for seed in SEEDS:
                        rows.extend(execute(seed,pattern,scenario,profile,cooling));groups+=1
                    print(f'{groups}/800 groups; {len(rows)} evaluations; {time.monotonic()-start:.1f}s',flush=True)
    assert len(rows)==5600;write_rows(OUT/'runs.csv',rows)
    sensitivity=[];equal=[]
    for profile in ('generic','apple_inspired'):
        for scenario in ('high_to_low','accurate_to_low'):
            for seed in SEEDS:
                sensitivity.extend(execute(seed,'bursty',scenario,profile,cost='zero_cost'))
                equal.extend(execute(seed,'bursty',scenario,profile,controllers=('periodic_20',),equal_completion_cost=True))
    assert len(sensitivity)==560 and len(equal)==80
    write_rows(OUT/'zero_cost.csv',sensitivity);write_rows(OUT/'equal_completion_cost.csv',equal)
    meta.update(completed=True,main_evaluations=len(rows),matched_groups=groups,
                zero_cost_evaluations=len(sensitivity),equal_completion_evaluations=len(equal),elapsed_s=time.monotonic()-start)
    (OUT/'settings.json').write_text(json.dumps(meta,indent=2)+'\n')
    print('Saved 5,600 main + 560 zero-cost + 80 equal-completion-cost evaluations.',flush=True)

if __name__=='__main__':main()
