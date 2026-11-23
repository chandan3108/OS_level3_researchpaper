from pathlib import Path
from dataclasses import asdict, replace
import csv, hashlib, json, math, random, time
from calibrated_study import Settings, make_case, simulate

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'results/calibrated'
SCENARIOS=('stationary_high','high_to_low','accurate_to_low','noise','mixed')
POLICIES=('uncorrected','legacy_guard','calibrated_static','calibrated_feedback')

def fingerprint(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def ratio(scenario, rng, t, work, seconds):
    if scenario=='stationary_high':return 1.3
    if scenario=='high_to_low':return 1.3 if t<seconds/2 else .7
    if scenario=='accurate_to_low':return 1. if t<seconds/2 else .7
    if scenario=='noise':return rng.lognormvariate(-.25**2/2,.25)
    if scenario=='mixed':return 1.3 if work<.024 else .7
    raise ValueError('unknown scenario')

def calibration(seed, scenario, n=20):
    rng=random.Random(700000+seed)
    history=[]
    for _ in range(n):
        work=rng.uniform(.018,.030)
        r=ratio(scenario,rng,0,work,20.)
        history.append({'observed_work':work,'estimate':work*r})
    gain=max(.5,min(2.,sum(x['observed_work']/x['estimate'] for x in history)/n))
    return gain,history

def workload(seed,pattern,scenario,seconds=20.):
    tasks,_=make_case(seed,pattern,'1.0',seconds)
    rng=random.Random(900000+seed)
    estimates=tuple(t.work*ratio(scenario,rng,t.arrival,t.work,seconds) for t in tasks)
    return tasks,estimates

def config(profile,cooling,overhead,gain):
    return Settings(apple_profile=int(profile=='apple_inspired'),initial_gain=gain,
        resistance_c_per_w=6. if cooling=='ordinary' else 18.,
        decision_cost_s=.00005 if overhead=='modeled_cost' else 0.,
        switch_cost_s=.0001 if overhead=='modeled_cost' else 0.,
        mode_switch_cost_s=.0002 if overhead=='modeled_cost' else 0.,
        feedback_update_cost_s=.00005 if overhead=='modeled_cost' else 0.)

def execute(seed,pattern,scenario,profile,cooling,overhead,record=False,e_factor=.65):
    tasks,estimates=workload(seed,pattern,scenario)
    gain,history=calibration(seed,scenario)
    base=replace(config(profile,cooling,overhead,gain),e_power_factor=e_factor)
    common=dict(seed=seed,pattern=pattern,scenario=scenario,profile=profile,cooling=cooling,overhead=overhead,
        calibration_gain=gain,calibration_count=len(history),calibration_sha256=fingerprint(history),
        task_sha256=fingerprint([asdict(t) for t in tasks]),estimate_sha256=fingerprint(estimates),
        shared_config_sha256=fingerprint(asdict(base)),e_power_factor=e_factor)
    output=[];traces={}
    for controller in POLICIES:
        policy='feedback' if controller=='calibrated_feedback' else 'guard'
        static_gain={'uncorrected':1.,'legacy_guard':1/.7,'calibrated_static':gain,'calibrated_feedback':gain}[controller]
        result,trace=simulate(policy,tasks,replace(base,guard_gain=static_gain),estimates,record)
        observations=result.pop('completion_observations',[])
        result.update(common,controller=controller)
        output.append(result)
        if record:traces[controller]={'states':trace,'observations':observations,'result':result}
    return output,traces,history

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    protocol=ROOT/'revisions/2026-10-30/SCOPE_AND_PROTOCOL.md'
    names=('calibrated_study.py','run_calibrated_study.py','study.py','revisions/2026-10-30/SCOPE_AND_PROTOCOL.md')
    meta={'protocol':str(protocol.relative_to(ROOT)),'native_testing':'ON HOLD',
          'physical_validation':False,'apple_parameters_calibrated':False,'seeds':list(range(100,120)),
          'source_sha256':{x:hashlib.sha256((ROOT/x).read_bytes()).hexdigest() for x in names},
          'primary_contrast':'calibrated_feedback minus calibrated_static','calibration_jobs':20,
          'research_question':'Under changing workloads, does completion-based correction reduce modeled energy while meeting a declared deadline requirement, compared with a static correction calibrated from the same historical data?',
          'parameter_assumptions':asdict(config('apple_inspired','ordinary','modeled_cost',1.))}
    (OUT/'settings.json').write_text(json.dumps(meta,indent=2)+'\n')
    rows=[];start=time.monotonic();groups=0
    for profile in ('generic','apple_inspired'):
        for cooling in ('ordinary','restricted'):
            for overhead in ('zero_cost','modeled_cost'):
                for pattern in ('bursty','poisson'):
                    for scenario in SCENARIOS:
                        for seed in range(100,120):
                            batch,_,_=execute(seed,pattern,scenario,profile,cooling,overhead)
                            rows.extend(batch);groups+=1
                        print(f'{groups}/1600 groups; {len(rows)} runs; {time.monotonic()-start:.1f}s',flush=True)
    assert len(rows)==6400
    with (OUT/'runs.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)

    sensitivity=[]
    for factor in (.5,.8,1.0):
        for scenario in ('stationary_high','high_to_low'):
            for seed in range(100,120):
                batch,_,_=execute(seed,'bursty',scenario,'apple_inspired','ordinary','modeled_cost',e_factor=factor)
                sensitivity.extend(batch)
    with (OUT/'sensitivity.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(sensitivity)
    meta.update(evaluations=len(rows),matched_groups=groups,sensitivity_evaluations=len(sensitivity),elapsed_s=time.monotonic()-start,completed=True)
    (OUT/'settings.json').write_text(json.dumps(meta,indent=2)+'\n')
    print('Saved 6,400 main evaluations plus 480 explicit E-power sensitivities.',flush=True)

if __name__=='__main__':main()
