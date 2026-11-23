import csv,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
HERE=ROOT/'results/periodic'
sys.path.insert(0,str(ROOT))
from run_calibrated_study import workload

def witness(tasks):
    ordered=sorted(tasks,key=lambda t:t.deadline);best=None
    for start in sorted({t.arrival for t in tasks}):
        work=count=0
        for task in ordered:
            if task.arrival<start-1e-12:continue
            work+=task.work;count+=1;end=task.deadline
            excess=work-(end-start)
            if excess>1e-9 and (best is None or excess>best['excess_work_s']):
                best=dict(interval_start_s=start,interval_end_s=end,required_work_s=work,
                          available_service_s=end-start,excess_work_s=excess,jobs=count)
    return best

def main():
    with (ROOT/'results/periodic/feasibility.csv').open() as stream:rows=list(csv.DictReader(stream))
    records=[]
    for row in rows:
        tasks,_=workload(int(row['seed']),row['pattern'],'stationary_high')
        proof=witness(tasks)
        assert bool(proof)==(row['pattern']=='poisson'),(row,proof)
        if proof:
            actual=[t for t in tasks if t.arrival>=proof['interval_start_s']-1e-12 and t.deadline<=proof['interval_end_s']+1e-12]
            assert len(actual)==proof['jobs']
            assert abs(sum(t.work for t in actual)-proof['required_work_s'])<1e-9
            assert proof['required_work_s']>proof['available_service_s']+1e-9
        records.append(dict(cohort=row['cohort'],seed=int(row['seed']),pattern=row['pattern'],overload_witness=proof))
    report=dict(streams_checked=len(records),poisson_infeasibility_witnesses=sum(bool(r['overload_witness']) for r in records),
                bursty_false_overload_witnesses=sum(bool(r['overload_witness']) for r in records if r['pattern']=='bursty'),
                proof='For contained jobs released no earlier than A and due no later than D, required work greater than D-A is impossible at maximum capacity one.',records=records)
    (HERE/'FEASIBILITY_CERTIFICATES.json').write_text(json.dumps(report,indent=2)+'\n')
    (ROOT/'report_ieee/generated').mkdir(parents=True,exist_ok=True)
    table=[r'\begin{tabular}{@{}lrrrr@{}}',r'\toprule',r'Seed & Start & End & Work & Capacity\\\midrule']
    for seed in (100,200):
        proof=next(r['overload_witness'] for r in records if r['seed']==seed and r['pattern']=='poisson')
        values=[1000*proof[k] for k in ('interval_start_s','interval_end_s','required_work_s','available_service_s')]
        table.append(str(seed)+' & '+' & '.join(f'{v:.3f}' for v in values)+r'\\')
    table.extend([r'\bottomrule',r'\end{tabular}'])
    (ROOT/'report_ieee/generated/feasibility_witness_table.tex').write_text('\n'.join(table)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='records'},indent=2))

if __name__=='__main__':main()
