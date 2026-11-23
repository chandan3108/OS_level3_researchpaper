import csv,os,tempfile
from pathlib import Path
os.environ.setdefault('MPLCONFIGDIR',str(Path(tempfile.gettempdir())/'os-jackfruit-matplotlib'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'report_ieee/images/periodic';OUT.mkdir(parents=True,exist_ok=True)
GEN=ROOT/'report_ieee/generated'; GEN.mkdir(parents=True,exist_ok=True)
OLD=list(csv.DictReader((ROOT/'results/calibrated/paired.csv').open()))
OLD_AGG=list(csv.DictReader((ROOT/'results/calibrated/aggregates.csv').open()))
NEW=list(csv.DictReader((ROOT/'results/periodic/paired.csv').open()))
AGG=list(csv.DictReader((ROOT/'results/periodic/aggregates.csv').open()))
FAMILY=list(csv.DictReader((ROOT/'results/periodic/primary_family.csv').open()))
SCENARIOS=('stationary_high','high_to_low','accurate_to_low','noise','mixed')
LABELS=('Stable overestimate','High to low','Accurate to low','Independent noise','Mixed biases')
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':12.5,'pdf.fonttype':42,
                     'axes.spines.top':False,'axes.spines.right':False})

def select(rows,**filters):
    return next(r for r in rows if all(r[k]==v for k,v in filters.items()))

def effect(ax,rows,metric,labels,scale=1,color='#245dce'):
    for i,row in enumerate(rows):
        value=float(row[metric+'_delta_mean'])*scale
        lo=row[metric+'_delta_ci_low'];hi=row[metric+'_delta_ci_high']
        if lo!='':
            left=max(0.,value-float(lo)*scale);right=max(0.,float(hi)*scale-value)
            ax.errorbar(value,i,xerr=np.array([[left],[right]]),fmt='o',color=color,capsize=3,ms=5)
        else:ax.plot(value,i,'s',color=color,ms=5)
    ax.set_yticks(range(len(labels)),labels);ax.invert_yaxis()
    ax.axvline(0,color='#777777',lw=.9,ls='--');ax.grid(axis='x',alpha=.2)
    ax.set_axisbelow(True);ax.margins(y=.17)

def save(fig,name):
    fig.savefig(OUT/(name+'.pdf'),bbox_inches='tight')
    fig.savefig(OUT/(name+'.png'),dpi=190,bbox_inches='tight');plt.close(fig)

fig,axes=plt.subplots(3,2,figsize=(10.4,6.7),gridspec_kw={'height_ratios':(1.1,.65,1.1)})
for col,cooling in enumerate(('ordinary','restricted')):
    subset=[select(OLD,profile='apple_inspired',cooling=cooling,overhead='modeled_cost',pattern='bursty',scenario=s,baseline='calibrated_static') for s in SCENARIOS]
    effect(axes[0,col],subset,'deadline_miss_pct',LABELS)
    effect(axes[1,col],subset[3:],'deadline_miss_pct',('Noise','Mixed'))
    effect(axes[2,col],subset,'estimated_j_per_task',LABELS,1000)
    axes[0,col].set_title(cooling.capitalize()+' cooling')
    axes[0,col].set_xlabel('Miss difference (percentage points)')
    axes[1,col].set_title('Noise and mixed: enlarged scale',fontsize=12)
    axes[1,col].set_xlabel('Miss difference (percentage points)')
    axes[2,col].set_xlabel('Energy difference (mJ/task)')
fig.suptitle('Online feedback minus calibrated static · negative favors feedback',fontsize=13.5)
fig.tight_layout(rect=(0,0,1,.96),h_pad=1.0,w_pad=2.0);save(fig,'equal_history_paired')

baselines=('periodic_5','periodic_20','periodic_50','rolling_20')
names=('Batch 5','Batch 20 (primary)','Batch 50','Rolling 20')
fig,axes=plt.subplots(3,2,figsize=(10.4,6.7),gridspec_kw={'height_ratios':(1.1,.8,1.1)})
for col,scenario in enumerate(('high_to_low','accurate_to_low')):
    subset=[select(NEW,profile='apple_inspired',cooling='ordinary',overhead='modeled_cost',pattern='bursty',scenario=scenario,baseline=b) for b in baselines]
    effect(axes[0,col],subset,'deadline_miss_pct',names,color='#087f74')
    effect(axes[1,col],[subset[i] for i in (0,1,3)],'deadline_miss_pct',('Batch 5','Batch 20','Rolling 20'),color='#087f74')
    effect(axes[2,col],subset,'estimated_j_per_task',names,1000,color='#087f74')
    axes[0,col].set_title('High to low' if scenario=='high_to_low' else 'Accurate to low')
    axes[0,col].set_xlabel('Miss difference (percentage points)')
    axes[1,col].set_title('Near-zero cases: enlarged scale',fontsize=12)
    axes[1,col].set_xlabel('Miss difference (percentage points)')
    axes[2,col].set_xlabel('Energy difference (mJ/task)')
fig.suptitle('Fresh seeds · online feedback minus recalibration alternatives',fontsize=13.5)
fig.tight_layout(rect=(0,0,1,.96),h_pad=1.0,w_pad=2.0);save(fig,'recalibration_paired')

def table(name,columns,header,rows):
    lines=[r'\renewcommand{\arraystretch}{1.15}',r'\begin{tabular}{@{}'+columns+r'@{}}',r'\toprule',header+r'\\',r'\midrule']
    lines += [' & '.join(r)+r'\\' for r in rows]
    lines += [r'\bottomrule',r'\end{tabular}']
    (GEN/name).write_text('\n'.join(lines)+'\n')

rows=[]
for scenario,label in zip(SCENARIOS,('Stable high','High to low','Accurate to low','Noise','Mixed')):
    pair=select(OLD,profile='apple_inspired',cooling='ordinary',overhead='modeled_cost',pattern='bursty',scenario=scenario,baseline='calibrated_static')
    a=select(OLD_AGG,profile='apple_inspired',cooling='ordinary',overhead='modeled_cost',pattern='bursty',scenario=scenario,controller='calibrated_static')
    b=select(OLD_AGG,profile='apple_inspired',cooling='ordinary',overhead='modeled_cost',pattern='bursty',scenario=scenario,controller='calibrated_feedback')
    rows.append([label,f"{float(a['estimated_j_per_task_mean']):.5f}",f"{float(b['estimated_j_per_task_mean']):.5f}",
                 f"{float(a['deadline_miss_pct_mean']):.2f}",f"{float(b['deadline_miss_pct_mean']):.2f}",
                 pair['baseline_zero_miss_runs']+'/'+pair['feedback_zero_miss_runs']])
table('calibrated_primary_zero_table.tex','lrrrrr',r'Error & $E_S$ & $E_F$ & $M_S$ & $M_F$ & $Z_S/Z_F$',rows)

rows=[]
for scenario,label in zip(SCENARIOS,('Stable high','High to low','Accurate to low','Noise','Mixed')):
    r=select(OLD,profile='apple_inspired',cooling='ordinary',overhead='modeled_cost',pattern='bursty',scenario=scenario,baseline='legacy_guard')
    rows.append([label,f"{float(r['estimated_j_per_task_delta_mean']):+.5f}",f"{float(r['deadline_miss_pct_delta_mean']):+.2f}",r['feedback_zero_miss_runs']+'/'+r['baseline_zero_miss_runs']])
table('legacy_guard_closure_table.tex','lrrr',r'Error & $\Delta E$ & $\Delta M$ & $Z_F/Z_G$',rows)

rows=[]
for profile,label in [('generic','Generic'),('apple_inspired','Apple')]:
    for cooling in ('ordinary','restricted'):
        r=select(OLD,profile=profile,cooling=cooling,overhead='modeled_cost',pattern='poisson',scenario='mixed',baseline='calibrated_static')
        rows.append([label,'Ordinary' if cooling=='ordinary' else 'Restricted',f"{float(r['estimated_j_per_task_delta_mean']):+.5f}",f"{float(r['deadline_miss_pct_delta_mean']):+.2f}"])
table('poisson_mixed_table.tex','llrr',r'Profile & Cooling & $\Delta E$ & $\Delta M$',rows)

rows=[]
for controller,label in [('calibrated_static','Calibrated static'),('calibrated_feedback','EWMA feedback'),('periodic_5','Batch 5'),('periodic_20','Batch 20 (primary)'),('periodic_50','Batch 50'),('rolling_20','Rolling 20'),('legacy_guard','Legacy guard')]:
    values=[]
    for scenario in ('high_to_low','accurate_to_low'):
        r=select(AGG,profile='apple_inspired',cooling='ordinary',overhead='modeled_cost',pattern='bursty',scenario=scenario,controller=controller)
        values += [f"{float(r['estimated_j_per_task_mean']):.5f}",f"{float(r['deadline_miss_pct_mean']):.3f}",r['zero_miss_runs']+'/20']
    rows.append([label]+values)
table('fresh_recalibration_table.tex','lrrrrrr',r'Controller & \multicolumn{3}{c}{High to low} & \multicolumn{3}{c}{Accurate to low}\\'+ '\n'+r' & J/task & Miss (\%) & Zero-miss runs & J/task & Miss (\%) & Zero-miss runs',rows)

def pformat(value):
    value=float(value)
    return f'{value:.2g}' if value<.001 else f'{value:.3f}'
rows=[]
for r in FAMILY:
    pair=select(NEW,profile=r['profile'],cooling='ordinary',overhead='modeled_cost',pattern='bursty',scenario=r['scenario'],baseline='periodic_20')
    metric=r['endpoint'];v=float(pair[metric+'_delta_mean'])
    rows.append(['Apple' if r['profile']=='apple_inspired' else 'Generic','High/low' if r['scenario']=='high_to_low' else 'Acc./low',
                 'Energy' if metric=='estimated_j_per_task' else 'Miss',f'{v:+.5f}' if metric=='estimated_j_per_task' else f'{v:+.3f}',
                 r['negative_n']+'/'+r['positive_n']+'/'+r['tied_n'],pformat(r['holm_p'])])
table('fresh_primary_family_table.tex','lllrlr',r'Profile & Shift & Endpoint & $\Delta$ & $-/+/=$ & $p_H$',rows)


ZERO=list(csv.DictReader((ROOT/'results/periodic/zero_cost_paired.csv').open()))
rows=[]
for profile,label in [('generic','Generic'),('apple_inspired','Apple')]:
    for scenario,shift in [('high_to_low','High/low'),('accurate_to_low','Acc./low')]:
        filters=dict(profile=profile,cooling='ordinary',pattern='bursty',scenario=scenario,baseline='periodic_5')
        modeled=select(NEW,**filters);zero=select(ZERO,**filters)
        assert zero['deadline_miss_pct_delta_variation']=='constant' and float(zero['deadline_miss_pct_delta_mean'])==0
        rows.append([label,shift,f"{1000*float(modeled['estimated_j_per_task_delta_mean']):.3f}",
                     f"{1000*float(zero['estimated_j_per_task_delta_mean']):.3f}",'0.000'])
table('batch5_cost_sensitivity_table.tex','llrrr',
      r'Profile & Shift & \shortstack{Saving\\costs on} & \shortstack{Saving\\costs off} & \shortstack{Miss change\\costs off}',rows)



rows=[]
for profile,label in [('generic','Generic'),('apple_inspired','Apple-inspired')]:
    for pattern,cooling,scenario,description in (
        ('bursty','restricted','high_to_low','High to low'),
        ('bursty','restricted','mixed','Mixed'),
        ('poisson','ordinary','mixed','Mixed'),
        ('poisson','restricted','mixed','Mixed')):
        r=select(NEW,profile=profile,cooling=cooling,pattern=pattern,scenario=scenario,baseline='periodic_20')
        rows.append([label,pattern.capitalize(),cooling.capitalize(),description.replace('High to low','High/low'),
                     f"{1000*float(r['estimated_j_per_task_delta_mean']):+.3f}",
                     f"{float(r['deadline_miss_pct_delta_mean']):+.3f}"])
        assert r['feedback_zero_miss_runs']==r['baseline_zero_miss_runs']=='0'
table('fresh_stress_table.tex','llllrr',
      r'Profile & Arrivals & Cooling & Error & $\Delta E$ & $\Delta M$',rows)
p=GEN/'fresh_stress_table.tex'
p.write_text(r'\setlength{\tabcolsep}{3.2pt}'+'\n'+p.read_text())
print('Saved two paired-CI figures and seven data-generated manuscript tables.')
