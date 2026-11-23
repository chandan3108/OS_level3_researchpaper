import csv
import math
from pathlib import Path
from run_periodic_study import execute, write_rows
from analyze_periodic_study import contrast

ROOT = Path(__file__).resolve().parent
HERE = ROOT / 'results/periodic'

def main():
    (ROOT/'report_ieee/generated').mkdir(parents=True,exist_ok=True)
    with (HERE/'runs.csv').open() as stream:
        original = list(csv.DictReader(stream))
    posthoc=[];effects=[];feedback_matches=0
    original_index={tuple(r[k] for k in ('seed','profile','scenario','cooling','pattern','controller')):r for r in original}
    for profile in ('generic','apple_inspired'):
        for scenario in ('high_to_low','accurate_to_low'):
            group=[]
            for seed in range(200,220):
                fresh=execute(seed,'bursty',scenario,profile,controllers=('calibrated_feedback','periodic_5'),equal_completion_cost=True)
                assert len({r['shared_config_sha256'] for r in fresh})==1
                for field in ('task_sha256','estimate_sha256','calibration_sha256'):
                    assert len({r[field] for r in fresh})==1
                old=original_index[(str(seed),profile,scenario,'ordinary','bursty','calibrated_feedback')]
                for field in ('estimated_j_per_task','deadline_miss_pct','overhead_time_s','completion_time_s','correction_updates'):
                    assert math.isclose(fresh[0][field],float(old[field]),rel_tol=1e-12,abs_tol=1e-12),field
                feedback_matches+=1;group.extend(fresh);posthoc.extend(fresh)
            a={r['seed']:r for r in group if r['controller']=='calibrated_feedback'}
            b={r['seed']:r for r in group if r['controller']=='periodic_5'}
            effects.append(contrast(a,b,dict(profile=profile,scenario=scenario,pattern='bursty',cooling='ordinary',
                overhead='equal_completion_cost',target='calibrated_feedback',baseline='periodic_5',posthoc=True)))
    write_rows(HERE/'batch5_equal_completion_runs.csv',posthoc)
    write_rows(HERE/'batch5_equal_completion_paired.csv',effects)
    table=[r'\begin{tabular}{@{}llrrr@{}}',r'\toprule',
           r'Profile & Shift & $\Delta E$ & $\Delta M$ & W/L/T\\\midrule']
    for row in effects:
        profile='Apple-inspired' if row['profile']=='apple_inspired' else 'Generic'
        scenario='High/low' if row['scenario']=='high_to_low' else 'Accurate/low'
        table.append(f"{profile} & {scenario} & {1000*row['estimated_j_per_task_delta_mean']:+.3f} & {row['deadline_miss_pct_delta_mean']:+.3f} & {row['joint_better']}/{row['joint_worse']}/{row['tradeoff_or_tie']}\\\\")
    table.extend([r'\bottomrule',r'\end{tabular}'])
    (ROOT/'report_ieee/generated/batch5_equal_completion_table.tex').write_text('\n'.join(table)+'\n')

    assert feedback_matches == 80 and len(posthoc) == 160

if __name__ == '__main__':
    main()
