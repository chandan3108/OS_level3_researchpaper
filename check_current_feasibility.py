import csv,heapq,json
from dataclasses import replace
from pathlib import Path
from calibrated_study import Settings,simulate
from run_calibrated_study import workload,fingerprint
from dataclasses import asdict

ROOT=Path(__file__).resolve().parent

def exact_edf(tasks):
    ordered=sorted(enumerate(tasks),key=lambda x:x[1].arrival)
    ready=[];i=missed=0;now=0.
    while i<len(ordered) or ready:
        if not ready:now=max(now,ordered[i][1].arrival)
        while i<len(ordered) and ordered[i][1].arrival<=now+1e-12:
            index,t=ordered[i];heapq.heappush(ready,(t.deadline,index,t.work));i+=1
        deadline,index,left=heapq.heappop(ready)
        next_arrival=ordered[i][1].arrival if i<len(ordered) else float('inf')
        duration=min(left,max(0.,next_arrival-now));now+=duration;left-=duration
        if left<=1e-12:missed+=now>deadline+1e-9
        else:heapq.heappush(ready,(deadline,index,left))
    return dict(tasks=len(tasks),missed_tasks=missed,deadline_miss_pct=100*missed/len(tasks))

def main():
    out=ROOT/'results/periodic';out.mkdir(exist_ok=True);rows=[]
    for cohort,seeds in [('previous',range(100,120)),('fresh',range(200,220))]:
        for pattern in ('bursty','poisson'):
            for seed in seeds:
                tasks,est=workload(seed,pattern,'stationary_high')
                exact=exact_edf(tasks)
                measured,_=simulate('performance',tasks,Settings(protection_enabled=False,decision_cost_s=0,switch_cost_s=0),est)
                assert exact['tasks']-exact['missed_tasks']==measured['on_time_tasks'],(cohort,pattern,seed)
                rows.append(dict(cohort=cohort,pattern=pattern,seed=seed,**exact,
                                 zero_miss_feasible=exact['missed_tasks']==0,
                                 task_sha256=fingerprint([asdict(t) for t in tasks])))
    with (out/'feasibility.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    summary={}
    for cohort in ('previous','fresh'):
        for pattern in ('bursty','poisson'):
            subset=[r for r in rows if r['cohort']==cohort and r['pattern']==pattern]
            summary[cohort+'_'+pattern]=dict(streams=len(subset),zero_miss_feasible=sum(r['zero_miss_feasible'] for r in subset),
               mean_max_speed_miss_pct=sum(r['deadline_miss_pct'] for r in subset)/len(subset))
    summary['independent_event_and_tick_engines_match']=True
    summary['scope']='Zero-miss feasibility for the synthetic serial fully preemptive model. Retained-job EDF miss count is not a lower bound on every policy miss count.'
    (out/'feasibility_summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))

if __name__=='__main__':main()
