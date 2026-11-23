import csv,hashlib,inspect,json,math,sys
from collections import defaultdict
from dataclasses import asdict,replace
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from periodic_study import Settings,Correction,CONTROLLERS,simulate
from run_periodic_study import execute
from run_calibrated_study import calibration,workload,config,fingerprint,ratio
from calibrated_study import request_frequency
from study import thermal_segment
from analyze_periodic_study import contrast,directional_test,holm_adjust

DEFAULT=dict(profile='apple_inspired',cooling='ordinary',pattern='bursty',scenario='high_to_low',overhead='modeled_cost')
CHOICES=dict(profile=('apple_inspired','generic'),cooling=('ordinary','restricted'),pattern=('bursty','poisson'),
 scenario=('stationary_high','high_to_low','accurate_to_low','noise','mixed'),overhead=('modeled_cost','zero_cost'))
METHODS=[
 dict(id='calibrated_feedback',label='Completion feedback',short='Feedback',color='#2563eb',rule='80% previous gain + 20% latest completed ratio',when='After every completion',detail='Smooths each new observation. It reacts gradually; it can also chase noise.'),
 dict(id='periodic_5',label='Recalibrate every 5 tasks',short='Batch 5',color='#087f72',rule='Mean of 5 newly completed ratios',when='Every 5 completions',detail='Holds its gain between batches. The last incomplete batch does not update.'),
 dict(id='periodic_20',label='Recalibrate every 20 tasks',short='Batch 20',color='#7c3aed',rule='Mean of 20 newly completed ratios',when='Every 20 completions',detail='The paper’s declared primary comparator. Its batch size matches the initial history size.'),
 dict(id='periodic_50',label='Recalibrate every 50 tasks',short='Batch 50',color='#b66516',rule='Mean of 50 newly completed ratios',when='Every 50 completions',detail='Uses a larger nonoverlapping batch. It can take longer to react to a shift.'),
 dict(id='rolling_20',label='Rolling window of 20 tasks',short='Rolling 20',color='#b74678',rule='Mean of the latest 20 completed ratios',when='After every completion',detail='Starts with the calibration history, removes the oldest ratio, and inserts the new one.'),
 dict(id='calibrated_static',label='Calibrated, then frozen',short='Frozen',color='#64748b',rule='Keep the shared starting gain',when='No evaluation updates',detail='Corrects a stable common bias, but cannot change after its history becomes stale.'),
 dict(id='legacy_guard',label='Legacy fixed guard',short='Guard',color='#475569',rule='Always multiply estimates by 1 / 0.7',when='Never updates',detail='A permanently conservative reference. It can meet more deadlines while using more energy.'),
]
SCENARIOS={
 'stationary_high':dict(label='Stable overestimates',short='Stable high',description='Every estimate is 30% too high throughout the run. Initial history already reveals that common bias.'),
 'high_to_low':dict(label='High → low estimates',short='High to low',description='Estimates begin 30% too high. Jobs arriving from 10 s onward have estimates 30% too low. This is a deliberately constructed change in estimation error.'),
 'accurate_to_low':dict(label='Accurate → low estimates',short='Accurate to low',description='Estimates begin accurate. At 10 s, newly arriving jobs are underestimated by 30%.'),
 'noise':dict(label='Independent random error',short='Random error',description='Each task has a separate mean-one lognormal error (log SD 0.25). A single correction cannot predict each independent error. The unclipped mean reciprocal is about 1.0645.'),
 'mixed':dict(label='Mixed task-family errors',short='Mixed biases',description='Work below 24 ms is overestimated by 30%; larger work is underestimated by 30%. One shared gain must compromise. The irregular stream also changes the family mixture relative to calibration.'),
}

def validate_context(value):
    if not isinstance(value,dict):raise ValueError('Settings must be an object.')
    out={}
    for key,allowed in CHOICES.items():
        v=value.get(key,DEFAULT[key])
        if v not in allowed:raise ValueError(f'Choose a supported {key}.')
        out[key]=v
    return out

def validate_run(value):
    out=validate_context(value)
    seed=value.get('seed',200);repeats=value.get('repeats',1)
    if type(seed) is not int or not 0<=seed<=1_000_000:raise ValueError('Seed must be a whole number from 0 to 1,000,000.')
    if type(repeats) is not int or repeats not in (1,5,20):raise ValueError('Choose 1, 5 or 20 generated workloads.')
    return out,seed,repeats

def key(context):return '|'.join(str(context[k]) for k in ('profile','cooling','pattern','scenario','overhead'))

def typed(row):
    out={}
    for k,v in row.items():
        if v=='':out[k]=None;continue
        try:
            number=float(v)
            out[k]=int(number) if number.is_integer() else number
        except (ValueError,TypeError):out[k]=v
    return out

def read_csv(name):
    with (ROOT/name).open() as f:return [typed(r) for r in csv.DictReader(f)]

def summarize(rows,context):
    grouped=defaultdict(dict)
    for row in rows:
        seed=int(row['seed']);assert seed not in grouped[row['controller']]
        grouped[row['controller']][seed]=row
    assert set(grouped)==set(CONTROLLERS)
    seeds=sorted(next(iter(grouped.values())))
    for seed in seeds:
        match=[g[seed] for g in grouped.values()]
        for field in ('task_sha256','estimate_sha256','calibration_sha256','shared_config_sha256','tasks','horizon_s'):
            assert len({str(r[field]) for r in match})==1,field
    aggregates=[]
    metrics=('estimated_j_per_task','deadline_miss_pct','overhead_time_s','estimated_peak_c','p95_latency_ms','mode_switches','correction_updates')
    for method in CONTROLLERS:
        values=grouped[method]
        record=dict(context,controller=method,n=len(seeds))
        for metric in metrics:record[metric+'_mean']=sum(float(values[s][metric]) for s in seeds)/len(seeds)
        record['zero_miss_runs']=sum(float(values[s]['deadline_miss_pct'])==0 for s in seeds)
        aggregates.append(record)
    pairs=[contrast(grouped['calibrated_feedback'],grouped[b],dict(context,target='calibrated_feedback',baseline=b)) for b in CONTROLLERS if b!='calibrated_feedback']
    return dict(context=context,aggregates=aggregates,pairs=pairs,n=len(seeds),seeds=seeds,
                source='new_python',family=[],matched_inputs=True,policy_evaluations=len(rows),
                note='New software-model experiment. Intervals are pointwise exploratory bootstrap intervals; the published Holm family is not recomputed for custom runs.')

def run_experiment(value,progress=lambda done,total:None):
    context,seed,repeats=validate_run(value);rows=[]
    for i in range(repeats):
        rows.extend(execute(seed+i,context['pattern'],context['scenario'],context['profile'],context['cooling'],context['overhead']))
        progress(i+1,repeats)
    return summarize(rows,context),rows

def replay(context,seed=200,baseline='periodic_20'):
    context=validate_context(context)
    if baseline not in CONTROLLERS or baseline=='calibrated_feedback':raise ValueError('Choose a comparator other than feedback.')
    if type(seed) is not int or not 0<=seed<=1_000_000:raise ValueError('Invalid seed.')
    tasks,estimates=workload(seed,context['pattern'],context['scenario'])
    gain,history=calibration(seed,context['scenario'])
    cfg=Settings(**asdict(config(context['profile'],context['cooling'],context['overhead'],gain)))
    if context['overhead']=='zero_cost':cfg=replace(cfg,completion_observation_cost_s=0.,recalibration_application_cost_s=0.)
    original=execute(seed,context['pattern'],context['scenario'],context['profile'],context['cooling'],context['overhead'],controllers=('calibrated_feedback',baseline))
    packed={}
    for method,expected in zip(('calibrated_feedback',baseline),original):
        result,states=simulate(method,tasks,cfg,estimates,history,record_trace=True)
        observations=result.pop('completion_observations',[])
        for metric in ('estimated_j_per_task','deadline_miss_pct','overhead_time_s','completion_time_s'):
            assert math.isclose(result[metric],expected[metric],rel_tol=1e-12,abs_tol=1e-12),(method,metric)
        kept=[dict(time_s=0.,temperature_c=cfg.initial_c,frequency_fraction=0.,queue_length=0,
                   feedback_gain=gain,energy_j=0.,protection_active=0,requested_capacity=0.,execution_class='idle',overhead_time_s=0.)]
        kept+=states[::5]
        if kept[-1]!=states[-1]:kept.append(states[-1])
        last=states[-1]
        for t in list(range(math.floor(last['time_s'])+1,40))+[40]:
            if t<=last['time_s']:continue
            temperature,_=thermal_segment(last['temperature_c'],cfg.idle_w,t-last['time_s'],cfg)
            kept.append(dict(last,time_s=t,temperature_c=temperature,frequency_fraction=0,queue_length=0,
                             requested_capacity=0,execution_class='idle',protection_active=0,
                             energy_j=result['estimated_energy_j'] if t==40 else last['energy_j']+cfg.idle_w*(t-last['time_s'])))
        packed[method]=dict(states=kept,observations=observations,result=result)
    sample_indices=list(range(min(5,len(tasks))))+[i for i,t in enumerate(tasks) if t.arrival>=10][:5]
    samples=[dict(arrival_ms=tasks[i].arrival*1000,deadline_ms=tasks[i].deadline*1000,
                  actual_work_ms=tasks[i].work*1000,estimate_ms=estimates[i]*1000) for i in sample_indices]
    return dict(context=context,seed=seed,baseline=baseline,initial_gain=gain,history=history,
                traces=packed,tasks=len(tasks),sample_jobs=samples,source='python_trace',
                sampling='Queue, capacity and temperature sampled at roughly 100 ms; gain changes use exact completion observations.',
                truth_note='Actual-work sample values are generator ground truth, unavailable to the controller before completion.')

def source_excerpt(obj,title,explanation):
    lines,line=inspect.getsourcelines(obj);path=Path(inspect.getfile(obj)).resolve()
    return dict(title=title,explanation=explanation,path=str(path.relative_to(ROOT)),line=line,
                code=''.join(lines),sha256=hashlib.sha256(path.read_bytes()).hexdigest())

def build_payload():
    aggregates=read_csv('results/periodic/aggregates.csv');pairs=read_csv('results/periodic/paired.csv')
    family=read_csv('results/periodic/primary_family.csv')
    cases={}
    for row in aggregates:
        context={k:row[k] for k in CHOICES};k=key(context)
        cases.setdefault(k,dict(context=context,aggregates=[],pairs=[],family=[],n=20,seeds=list(range(200,220)),source='paper',matched_inputs=True))['aggregates'].append(row)
    for row in pairs:cases[key(row)]['pairs'].append(row)
    for row in family:cases[key(row)]['family'].append(row)

    raw_zero=read_csv('results/periodic/zero_cost.csv');groups=defaultdict(list)
    for row in raw_zero:groups[key(row)].append(row)
    for k,rows in groups.items():
        context={name:rows[0][name] for name in CHOICES};record=summarize(rows,context)
        record.update(source='paper_zero_cost',note='Published zero-cost sensitivity; the eight-test family applies only to modeled-cost conditions.')
        cases[k]=record
    snippets={
      'correction':source_excerpt(Correction.observe_completion,'Completion correction','The same function implements EWMA, nonoverlapping batches and the rolling window.'),
      'costs':source_excerpt(Correction.completion_cost,'Cost of learning','Batch observation and application costs are explicit assumptions, not measurements.'),
      'capacity':source_excerpt(request_frequency,'Deadline demand and recovery','Only controller job views are passed in. They contain estimates and delivered service, not unfinished actual work.'),
      'calibration':source_excerpt(calibration,'Equal starting information','Both primary methods receive the same twenty completed synthetic historical tasks.'),
      'workload':source_excerpt(workload,'Generate the evaluation inputs','Task generation and estimation errors use separate seeded random streams.'),
      'errors':source_excerpt(ratio,'Construct the estimation errors','The five error processes are deliberate synthetic conditions, not a real runtime predictor.'),
      'runner':source_excerpt(execute,'Run all seven strategies','The existing paper runner is imported directly for new website experiments.'),
      'thermal':source_excerpt(thermal_segment,'Thermal accounting','Exact RC segments under the assumed power/temperature model.'),
      'tests':source_excerpt(directional_test,'Directional sign test','Negative, positive and tied pairs are counted explicitly. This does not test deadline noninferiority.'),
      'holm':source_excerpt(holm_adjust,'Eight-endpoint Holm adjustment','The declared family contains four conditions times two endpoints. Custom website runs stay exploratory.'),
    }
    return dict(title='Completion Feedback versus Periodic Recalibration',authors='Chandan N · Dhruv',
        institution='PES University · CSE (AIML)',default=DEFAULT,methods=METHODS,scenarios=SCENARIOS,cases=cases,
        snippets=snippets,default_replay=replay(DEFAULT),
        provenance=dict(paper_sha256=hashlib.sha256((ROOT/'report_ieee/OS_Project_IEEE_Report_Periodic_Recalibration.pdf').read_bytes()).hexdigest(),
          main_evaluations=5600,cost_sensitivity_evaluations=640,conditions=40,seeds_per_condition=20,
          feasibility=json.loads((ROOT/'results/periodic/feasibility_summary.json').read_text()),
          publication=dict(posthoc_effects=read_csv('results/periodic/batch5_equal_completion_paired.csv')),
          physical_validation=False,native_testing='ON HOLD'))
