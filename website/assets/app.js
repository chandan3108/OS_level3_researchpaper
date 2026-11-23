'use strict';
(() => {
 const D=window.PROJECT_STUDY;
 const $=id=>document.getElementById(id);
 const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const fmt=(value,digits=3)=>Number(value).toLocaleString('en-US',{minimumFractionDigits:digits,maximumFractionDigits:digits});
 const signed=(value,digits=3)=>`${Number(value)>0?'+':''}${fmt(value,digits)}`;
 const M=Object.fromEntries(D.methods.map(m=>[m.id,m]));
 const ids=['profile','cooling','pattern','scenario','overhead'];
 const key=c=>ids.map(k=>c[k]).join('|');
 const context=()=>Object.fromEntries(ids.map(id=>[id,$(id).value]));
 const profileLabel=p=>p==='apple_inspired'?'Apple-inspired serial E/P':'Generic single worker';
 const patternLabel=p=>p==='bursty'?'bursty arrivals':'irregular arrivals';
 const coolingLabel=c=>c==='ordinary'?'ordinary cooling':'restricted cooling';
 const contextLabel=c=>`${profileLabel(c.profile)} · ${coolingLabel(c.cooling)} · ${patternLabel(c.pattern)} · ${c.overhead==='zero_cost'?'zero costs':'modeled costs'}`;
 let view='home',mode='paper',baseline='periodic_20',hasServer=false,busy=false;
 let result=D.cases[key(D.default)],replayData=D.default_replay,replayTime=0,playing=false,lastFrame=0,paintTime=0;
 let toastTimer,tourIndex=-1;
 const tourSteps=[
  ['home','Start with the question: estimates can be wrong. We test when updating after every completion is better than recalibrating in batches, using the same initial information.'],
  ['lab','The paper data are twenty paired workload averages. Compare feedback with Batch 20, then Batch 5. In the highlighted shift, Batch 5 uses less energy with nearly equal misses. Switch to a new Python experiment to generate and export actual rows.'],
  ['watch','Pause and use Next completion. Read the original estimate, the completed work and the updated gain. Batch 20 holds its gain until twenty observations have arrived. This is a single generated workload.'],
  ['methods','Explain the two separate decisions: EDF chooses the task, while demand chooses processing capacity. The correction rule supplies the estimate multiplier. The code snippets are extracted from the actual Python source.'],
  ['evidence','Finish with the scope: these are internally checked simulation results. Noise, mixed errors and cooling retain failures; the Apple model is assumed and physical validation is pending.']
 ];
 function toast(text){clearTimeout(toastTimer);$('toast').textContent=text;$('toast').hidden=false;toastTimer=setTimeout(()=>$('toast').hidden=true,4200);}
 function showError(id,text){$(id).textContent=text;$(id).hidden=!text;}
 function gotoView(next,scroll=true){
  if(!['home','lab','watch','methods','evidence'].includes(next))next='home';
  if(view==='watch'&&next!=='watch')pauseReplay();view=next;
  document.querySelectorAll('.page').forEach(p=>{p.hidden=p.id!==next;p.classList.toggle('active',p.id===next);});
  document.querySelectorAll('.nav-item').forEach(b=>{const active=b.dataset.view===next;b.classList.toggle('active',active);if(active)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current');});
  const labels={home:'The big picture',lab:'Experiment lab',watch:'Watch it work',methods:'Algorithms & code',evidence:'Paper & evidence'};
  $('section-label').textContent=labels[next];history.replaceState(null,'','#view='+next);
  if(next==='watch')renderReplay();if(scroll)window.scrollTo({top:0,behavior:'instant'});
 }
 function initControls(){
  $('scenario').innerHTML=Object.entries(D.scenarios).map(([id,s])=>`<option value="${id}">${esc(s.label)}</option>`).join('');
  $('baseline').innerHTML=D.methods.filter(m=>m.id!=='calibrated_feedback').map(m=>`<option value="${m.id}">${esc(m.label)}</option>`).join('');
  ids.forEach(id=>$(id).value=D.default[id]);$('baseline').value=baseline;
  ids.forEach(id=>$(id).addEventListener('change',settingsChanged));
  $('baseline').addEventListener('change',()=>{baseline=$('baseline').value;renderResults();});
  $('seed').addEventListener('input',()=>{if(mode==='custom')$('settings-status').textContent='Ready to generate';});
  $('repeats').addEventListener('change',()=>{if(mode==='custom')$('settings-status').textContent='Ready to generate';});
  settingsChanged();
 }
 function setMode(next){
  mode=next;
  document.querySelectorAll('[data-mode]').forEach(b=>{b.classList.toggle('selected',b.dataset.mode===next);b.setAttribute('aria-pressed',String(b.dataset.mode===next));});
  document.querySelectorAll('.custom-control').forEach(e=>e.hidden=next!=='custom');
  $('settings-title').textContent=next==='paper'?'Choose a published condition':'Generate a matched experiment';
  $('settings-description').textContent=next==='paper'?'Saved results from the final periodic-recalibration paper.':'Calls run_periodic_study.execute() for each generated workload. Original research CSVs are preserved.';
  if(next==='custom'&&!hasServer)showError('lab-error','Open this site through the local Python server to generate new experiments. Double-click Open_Project_Demo.command. Paper data and the saved default replay work offline.');
  else showError('lab-error','');settingsChanged();
 }
 function settingsChanged(){
  const c=context();const zeroAvailable=c.cooling==='ordinary'&&c.pattern==='bursty'&&['high_to_low','accurate_to_low'].includes(c.scenario);
  $('overhead').querySelector('[value="zero_cost"]').disabled=mode==='paper'&&!zeroAvailable;
  if(mode==='paper'&&!zeroAvailable&&c.overhead==='zero_cost'){
   $('overhead').value='modeled_cost';c.overhead='modeled_cost';toast('The published zero-cost sensitivity covers the ordinary-cooling bursty shifts. Showing modeled costs for this condition.');
  }
  $('cost-note').textContent=mode==='paper'&&!zeroAvailable?'Published zero-cost data cover only ordinary bursty shift cases.':'Decision, capacity-switching and learning costs are included when enabled.';
  $('scenario-description').textContent=D.scenarios[c.scenario].description;
  $('scenario-short').textContent=['high_to_low','accurate_to_low'].includes(c.scenario)?'The error changes for jobs arriving from 10 s.':'The selected error process applies across the run.';
  $('settings-status').textContent=mode==='paper'?'20 paired workloads':'Ready to generate';
  if(mode==='paper'){
   const next=D.cases[key(c)];if(next){result=next;renderResults();}
   else showError('lab-error','This setting is not in the published dataset. Use the Python experiment tab.');
  }
 }
 function renderHome(){
  const c=D.cases[key(D.default)],p=c.pairs.find(p=>p.baseline==='periodic_20');
  const b=c.aggregates.find(a=>a.controller==='periodic_20');
  const saving=-100*p.estimated_j_per_task_delta_mean/b.estimated_j_per_task_mean;
  $('home-findings').innerHTML=`<article class="card finding"><span class="eyebrow">FEEDBACK VS BATCH 20</span><div class="number">${fmt(saving,2)}%</div><span class="metric-label">lower modeled energy</span><p>High-to-low error, ordinary cooling and bursty arrivals. The improvement over a practical updating comparator is modest.</p></article><article class="card finding"><span class="eyebrow">DEADLINE PERFORMANCE</span><div class="number">${fmt(-p.deadline_miss_pct_delta_mean,3)} <small>pp</small></div><span class="metric-label">fewer missed deadlines</span><p>All 20 paired workloads improve on both outcomes in this condition. Some deadlines are still missed.</p></article><article class="card finding warning"><span class="eyebrow">THE IMPORTANT COUNTEREXAMPLE</span><div class="number">Batch 5</div><span class="metric-label">uses less energy than feedback</span><p>Its energy advantage remains when modeled overhead is removed. No correction schedule wins everywhere.</p></article>`;
 }
 function barChart(metric,digits){
  const records=D.methods.map(m=>({m,row:result.aggregates.find(a=>a.controller===m.id)}));
  const maximum=Math.max(...records.map(x=>x.row[metric+'_mean']),metric==='deadline_miss_pct'?1:.001)*1.1;
  return records.map(({m,row})=>{
   const value=row[metric+'_mean'];const highlight=m.id===baseline||m.id==='calibrated_feedback';
   return `<div class="bar-row ${highlight?'highlight':''}" role="img" aria-label="${esc(m.label)}: ${value} ${metric==='deadline_miss_pct'?'percent missed':'joules per task'}"><span class="bar-label" title="${esc(m.label)}">${esc(m.short)}</span><div class="bar-track"><div class="bar-fill ${value===0?'zero':''}" style="width:${100*value/maximum}%;background:${m.color};opacity:${highlight?1:.72}"></div></div><span class="bar-value">${fmt(value,digits)}</span></div>`;
  }).join('')+`<div class="bar-axis"><span>0</span><span>${fmt(maximum/2,metric==='deadline_miss_pct'?1:3)}</span><span>${fmt(maximum,metric==='deadline_miss_pct'?1:3)}</span></div>`;
 }
 function ciGauge(pair,metric,scale=1){
  const mean=pair[metric+'_delta_mean']*scale,lo=pair[metric+'_delta_ci_low'],hi=pair[metric+'_delta_ci_high'];
  const span=Math.max(Math.abs(mean),Math.abs((lo??mean/scale)*scale),Math.abs((hi??mean/scale)*scale),metric==='deadline_miss_pct'?.05:.005)*1.3;
  const x=v=>160+v/span*140;
  return `<svg class="ci-track" viewBox="0 0 320 35" role="img" aria-label="Paired mean difference and pointwise interval"><line x1="20" x2="300" y1="17" y2="17" stroke="#dbe3eb"/><line x1="160" x2="160" y1="4" y2="30" stroke="#82909f" stroke-dasharray="3 3"/>${lo!==null&&lo!==undefined?`<line x1="${x(lo*scale)}" x2="${x(hi*scale)}" y1="17" y2="17" stroke="#2563eb" stroke-width="3"/><line x1="${x(lo*scale)}" x2="${x(lo*scale)}" y1="11" y2="23" stroke="#2563eb"/><line x1="${x(hi*scale)}" x2="${x(hi*scale)}" y1="11" y2="23" stroke="#2563eb"/>`:''}<circle cx="${x(mean)}" cy="17" r="5" fill="${mean<=0?'#087f72':'#a74629'}"/></svg>`;
 }
 function renderResults(){
  if(!result)return;
  const c=result.context,p=result.pairs.find(p=>p.baseline===baseline),b=result.aggregates.find(a=>a.controller===baseline),f=result.aggregates.find(a=>a.controller==='calibrated_feedback');
  const de=p.estimated_j_per_task_delta_mean,dm=p.deadline_miss_pct_delta_mean,pct=100*de/b.estimated_j_per_task_mean;
  const isPaper=result.source.startsWith('paper');
  $('results-source').textContent=isPaper?(result.source==='paper_zero_cost'?'Paper zero-cost sensitivity':'Paper main dataset'):'New Python-generated experiment';
  $('results-context').textContent=D.scenarios[c.scenario].label;
  $('results-caption').textContent=`${contextLabel(c)} · ${result.n} paired workload${result.n===1?'':'s'} · seeds ${result.seeds[0]}${result.n>1?'–'+result.seeds.at(-1):''}`;
  $('kpi-grid').innerHTML=`<article class="card kpi-card"><span class="eyebrow">ENERGY VS ${esc(M[baseline].short.toUpperCase())}</span><div class="kpi-value" style="color:${de<=0?'#087f72':'#a74629'}">${fmt(Math.abs(pct),3)}% ${de<0?'lower':de>0?'higher':'change'}</div><small>Feedback’s mean energy per task</small></article><article class="card kpi-card"><span class="eyebrow">DEADLINE-MISS DIFFERENCE</span><div class="kpi-value" style="color:${dm<=0?'#087f72':'#a74629'}">${signed(dm,3)} pp</div><small>Percentage points, not relative percent</small></article><article class="card kpi-card"><span class="eyebrow">ZERO-MISS WORKLOADS</span><div class="kpi-value">${p.feedback_zero_miss_runs}/${result.n} <small>vs</small> ${p.baseline_zero_miss_runs}/${result.n}</div><small>Feedback versus ${esc(M[baseline].short)}</small></article>`;
  $('energy-chart').innerHTML=barChart('estimated_j_per_task',5);$('miss-chart').innerHTML=barChart('deadline_miss_pct',3);
  $('comparison-title').textContent=`Feedback minus ${M[baseline].short}`;
  $('comparison-stat').innerHTML=[['estimated_j_per_task','Energy per task','mJ/task',1000],['deadline_miss_pct','Deadline misses','percentage points',1]].map(([metric,label,unit,scale])=>{
   const mean=p[metric+'_delta_mean']*scale,lo=p[metric+'_delta_ci_low'],hi=p[metric+'_delta_ci_high'];
   return `<div class="comparison-stat"><h4>${label}</h4><div class="difference-value ${mean<=0?'good':'bad'}">${signed(mean,3)} <small>${unit}</small></div>${ciGauge(p,metric,scale)}<div class="ci-label">${lo!==null&&lo!==undefined?`Pointwise 95% interval: [${signed(lo*scale,3)}, ${signed(hi*scale,3)}]`:(result.n===1?'One workload: no between-workload interval.':'Constant difference: no interval displayed.')}</div></div>`;
  }).join('');
  let finding;
  if(de< -1e-9&&dm< -1e-9)finding=`Feedback uses less mean energy and has fewer mean misses in this condition.`;
  else if(de< -1e-9&&Math.abs(dm)<=1e-9)finding='Feedback uses less mean energy, with the same mean miss rate.';
  else if(de>1e-9&&dm>1e-9)finding=`${M[baseline].short} has lower mean energy and fewer mean misses here.`;
  else if(de>1e-9&&Math.abs(dm)<=1e-9)finding=`${M[baseline].short} uses less mean energy, with the same mean miss rate.`;
  else if(Math.abs(de)<=1e-9&&Math.abs(dm)<=1e-9)finding='The two methods match on both reported means.';
  else finding='This condition is a trade-off: one outcome improves while the other gets worse.';
  $('interpretation').className='interpretation'+((de*dm<0)?' tradeoff':'');
  $('interpretation').innerHTML=`<strong>${esc(finding)}</strong> Across individual paired workloads, feedback is jointly better in <strong>${p.joint_better}/${result.n}</strong>, jointly worse in <strong>${p.joint_worse}/${result.n}</strong>, and trades off or ties in <strong>${p.tradeoff_or_tie}/${result.n}</strong>. A mean result is not a guarantee for every task or future workload.`;
  $('interval-note').textContent=result.n===1?'Use 5 or 20 generated workloads to explore variation. The single workload is a demonstration, not a statistical study.':'Intervals describe variation across these generated workloads. They are pointwise, not simultaneous intervals, and do not cover uncertainty in the assumed physical constants.';
  $('table-sample-size').textContent=`${result.n} matched workload${result.n===1?'':'s'}`;
  $('results-table').innerHTML=`<thead><tr><th>Correction strategy</th><th class="numeric">Energy (J/task)</th><th class="numeric">Misses (%)</th><th class="numeric">Zero-miss workloads</th><th class="numeric">Overhead (ms)</th><th class="numeric">Gain updates</th></tr></thead><tbody>${D.methods.map(m=>{
   const a=result.aggregates.find(a=>a.controller===m.id);
   return `<tr class="${m.id==='calibrated_feedback'?'selected-row':m.id===baseline?'baseline-row':''}"><td><span class="method-dot" style="background:${m.color}"></span>${esc(m.label)}</td><td class="numeric">${fmt(a.estimated_j_per_task_mean,5)}</td><td class="numeric">${fmt(a.deadline_miss_pct_mean,3)}</td><td class="numeric">${a.zero_miss_runs}/${result.n}</td><td class="numeric">${fmt(a.overhead_time_s_mean*1000,2)}</td><td class="numeric">${fmt(a.correction_updates_mean,1)}</td></tr>`;
  }).join('')}</tbody>`;
  const notes=[];
  if(c.pattern==='poisson')notes.push('<strong>Feasibility context:</strong> every tested paper Poisson stream misses at least one deadline even at unconstrained maximum-capacity EDF. New custom seeds are not automatically covered by that diagnostic. Additional controller misses still matter.');
  if(c.cooling==='restricted')notes.push('<strong>Restricted cooling:</strong> the assumed heat-removal resistance is 18 rather than 6 °C/W. Thermal protection may cap capacity even when deadlines need more work.');
  if(c.scenario==='mixed')notes.push('<strong>Mixed errors:</strong> a single shared gain cannot correct both families perfectly. The irregular workload also changes family mixture relative to calibration.');
  if(c.scenario==='stationary_high')notes.push('<strong>Stable bias:</strong> the initial history already reveals the correction. Further updating can add overhead without new information.');
  if(c.overhead==='zero_cost')notes.push('<strong>Zero-cost sensitivity:</strong> removes all modeled controller/transition costs. It is not a measurement of actual implementation cost.');
  $('context-notes').innerHTML=notes.map(n=>`<p>${n}</p>`).join('');
  $('export-raw').hidden=!result.export_url;if(result.export_url)$('export-raw').href=result.export_url;
 }
 async function api(path,value){
  const options=value?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(value)}:{};
  const response=await fetch(path,options);const data=await response.json();if(!response.ok)throw new Error(data.error||'Request failed.');return data;
 }
 async function runExperiment(event){
  event.preventDefault();if(mode!=='custom')return;
  if(!hasServer){showError('lab-error','Start the local Python server with Open_Project_Demo.command to generate new experiments.');return;}
  if(busy)return;
  const seed=Number($('seed').value),repeats=Number($('repeats').value);
  if(!Number.isInteger(seed)||seed<0||seed>1000000){showError('lab-error','Enter a whole-number seed from 0 to 1,000,000.');return;}
  busy=true;[...ids,'seed','repeats'].forEach(id=>$(id).disabled=true);document.querySelectorAll('[data-mode]').forEach(b=>b.disabled=true);$('run-experiment').disabled=true;$('run-experiment').textContent='Running actual Python…';$('run-progress').hidden=false;$('progress-fill').style.width='0%';showError('lab-error','');
  try{
   const started=await api('/api/run',{...context(),seed,repeats});
   for(;;){
    await new Promise(resolve=>setTimeout(resolve,350));const status=await api('/api/jobs/'+started.id);
    $('progress-fill').style.width=`${100*status.completed/status.total}%`;
    $('progress-label').textContent=`${status.completed}/${status.total} matched workloads · ${status.completed*7}/${status.total*7} policy simulations`;
    if(status.status==='error')throw new Error(status.error);
    if(status.status==='complete')break;
   }
   result=await api('/api/jobs/'+started.id+'/result');renderResults();$('settings-status').textContent='Python experiment complete';
   $('progress-label').textContent=`Complete: ${result.n} matched workload${result.n===1?'':'s'}, ${result.policy_evaluations} actual policy evaluations. Original research files are unchanged.`;
   toast('Python experiment complete. The table and graphs now show your generated results.');
  }catch(error){showError('lab-error',error.message);$('progress-label').textContent='Experiment did not complete.';}
  finally{busy=false;[...ids,'seed','repeats'].forEach(id=>$(id).disabled=false);document.querySelectorAll('[data-mode]').forEach(b=>b.disabled=false);$('run-experiment').disabled=false;$('run-experiment').innerHTML='Run Python simulation <span aria-hidden="true">→</span>';}
 }
 function downloadTable(){
  const headers=['Source','Profile','Cooling','Arrival_pattern','Estimation_error','Controller_costs','Seeds','Strategy','Energy_J_per_task','Deadline_miss_percent','Zero_miss_workloads','Workloads','Modeled_overhead_ms','Correction_updates'];
  const rows=D.methods.map(m=>{const a=result.aggregates.find(a=>a.controller===m.id);return[result.source,...ids.map(k=>result.context[k]),result.seeds.join(';'),m.label,a.estimated_j_per_task_mean,a.deadline_miss_pct_mean,a.zero_miss_runs,result.n,a.overhead_time_s_mean*1000,a.correction_updates_mean];});
  const csv=[headers,...rows].map(row=>row.map(v=>'"'+String(v).replaceAll('"','""')+'"').join(',')).join('\r\n');
  const url=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download=`${result.source}-${result.context.scenario}-summary.csv`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
 }
 function before(array,t,field='time_s'){
  let lo=0,hi=array.length;while(lo<hi){const mid=(lo+hi)>>1;if(array[mid][field]<=t+1e-10)lo=mid+1;else hi=mid;}return lo-1;
 }
 function gainAt(method,t){
  if(method==='legacy_guard')return 1/.7;
  const obs=replayData.traces[method].observations,i=before(obs,t);return i<0?replayData.initial_gain:obs[i].new_gain;
 }
 function renderReplay(){
  $('replay-source').textContent=replayData.saved?'Saved Python replay':'Generated Python replay';
  const c=replayData.context;
  $('replay-context').textContent=`${D.scenarios[c.scenario].label} · ${coolingLabel(c.cooling)}`;
  $('replay-caption').textContent=`${profileLabel(c.profile)} · ${patternLabel(c.pattern)} · seed ${replayData.seed} · ${replayData.tasks} tasks. One example; not the multi-workload mean or a processor monitor.`;
  $('jump-shift').disabled=!['high_to_low','accurate_to_low'].includes(c.scenario);
  drawReplayCharts();renderReplayState();renderSampleJobs();
 }
 function renderReplayState(){
  const t=replayTime,c=replayData.context;
  $('replay-slider').value=String(t);$('replay-time').textContent=fmt(t,3)+' s';
  let narration;
  if(t===0)narration=replayData.baseline==='legacy_guard'?`Feedback starts from twenty completed historical tasks at gain ${fmt(replayData.initial_gain,3)}. The legacy guard instead uses its fixed 1 / 0.7 multiplier (${fmt(1/.7,3)}). Both face the same evaluation tasks.`:`Both strategies start with the same twenty completed historical tasks and gain ${fmt(replayData.initial_gain,3)}. The first arriving task is about to run.`;
  else if(t>=20)narration='New arrivals have stopped. Remaining work finishes, then idle energy is charged through the same 40 s window. Ending earlier does not shorten the energy accounting window.';
  else if(t>=10&&['high_to_low','accurate_to_low'].includes(c.scenario))narration='Newly arriving jobs now have estimates 30% too low. Each method learns only from completed jobs. Some jobs released before the shift can finish after it, so the correction does not change instantly at 10 s.';
  else if(c.scenario==='stationary_high')narration='The estimation bias is stable. Calibration already supplied the needed common correction; additional updates can add modeled cost without new information.';
  else if(c.scenario==='noise')narration='Each task has a separate random estimation error. The latest observation may differ from the next one; one shared gain cannot predict every error.';
  else if(c.scenario==='mixed')narration='Small and large tasks have different error directions. A shared correction multiplier must compromise between them.';
  else narration='The controller sees estimates and delivered service, not unfinished actual work. EDF runs the nearest-deadline task; completion reveals a ratio for future correction.';
  $('replay-narration').textContent=narration;
  const methods=['calibrated_feedback',replayData.baseline];
  $('replay-lanes').innerHTML=methods.map(method=>{
   const trace=replayData.traces[method],index=Math.max(0,before(trace.states,t)),s=trace.states[index];
   const i=before(trace.observations,t),o=i>=0?trace.observations[i]:null,count=i+1,g=gainAt(method,t),m=M[method];
   const capacity=s.frequency_fraction,execution=capacity===0?'Idle':c.profile==='apple_inspired'?(capacity<=.4?'E mode':'P mode'):'Single worker';
   let completion;
   if(['calibrated_static','legacy_guard'].includes(method))completion='<span class="eyebrow">FROZEN CORRECTION</span>The gain is held fixed. The scheduler still runs every task and uses the same recovery and thermal rules.';
   else if(!o)completion='<span class="eyebrow">WAITING FOR A COMPLETION</span>No evaluation task has completed yet. The shared historical gain is still in use.';
   else{
    completion=`<span class="eyebrow">LATEST COMPLETION · ${fmt(o.time_s,3)} s</span>Estimate ${fmt(o.estimate_ms,2)} work-ms · observed ${fmt(o.observed_work_ms,2)} work-ms.<br>Observed ratio = <strong>${fmt(o.observed_ratio,3)}</strong>.`;
    if(method==='calibrated_feedback')completion+=`<div class="completion-formula">0.8 × ${fmt(o.old_gain,3)} + 0.2 × ${fmt(o.observed_ratio,3)}<br>→ gain ${fmt(o.new_gain,3)}</div>`;
    else if(method.startsWith('periodic_')){
     const k=Number(method.split('_')[1]),pending=count%k;
     completion+=`<div class="completion-formula">${o.applied?'Batch applied at this completion.':'Holding the previous gain.'}</div>${pending}/${k} new observations toward the next batch.<div class="window-progress"><span style="width:${100*pending/k}%"></span></div>`;
    }else completion+=`<div class="completion-formula">Replace oldest ratio → mean of latest 20<br>gain ${fmt(o.new_gain,3)}</div>`;
   }
   return `<article class="card lane" style="--lane-color:${m.color}"><div class="lane-header"><h3>${esc(m.label)}</h3><span class="pill">${execution}</span></div><div class="gain-large">${fmt(g,3)} <small>gain</small></div><div class="lane-subtitle">${esc(m.rule)}</div><div class="lane-stats"><div class="lane-stat"><span>Modeled temperature</span><strong>${fmt(s.temperature_c,1)}°C</strong></div><div class="lane-stat"><span>Delivered / requested capacity</span><strong>${fmt(capacity,1)} / ${fmt(s.requested_capacity,1)}</strong></div><div class="lane-stat"><span>Tasks waiting / running</span><strong>${s.queue_length}</strong><div class="queue-dots">${'<i></i>'.repeat(Math.min(12,s.queue_length))}${s.queue_length>12?'<small>+</small>':''}</div></div><div class="lane-stat"><span>Thermal cap</span><strong>${s.protection_active?'Active':'Inactive'}</strong></div></div><div class="completion-box">${completion}</div></article>`;
  }).join('');
  document.querySelectorAll('.replay-cursor').forEach(line=>{const x=45+t/40*550;line.setAttribute('x1',x);line.setAttribute('x2',x);});
 }
 function lineChart(series,ymin,ymax,threshold=null){
  const W=620,H=220,x=t=>45+t/40*550,y=v=>185-(v-ymin)/(ymax-ymin)*165;
  const shift=['high_to_low','accurate_to_low'].includes(replayData.context.scenario);
  let html=`<svg class="line-chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Timeline plot of actual simulator observations">`;
  for(let i=0;i<=3;i++){const v=ymin+i*(ymax-ymin)/3;html+=`<line x1="45" x2="595" y1="${y(v)}" y2="${y(v)}" stroke="#e5ebf0"/><text x="36" y="${y(v)+4}" fill="#718292" text-anchor="end" font-size="11">${fmt(v,1)}</text>`;}
  for(const t of [0,10,20,30,40])html+=`<text x="${x(t)}" y="207" fill="#718292" text-anchor="middle" font-size="11">${t}s</text>`;
  if(shift)html+=`<line x1="${x(10)}" x2="${x(10)}" y1="20" y2="185" stroke="#a8b5bf" stroke-dasharray="4 4"/>`;
  if(threshold!==null)html+=`<line x1="45" x2="595" y1="${y(threshold)}" y2="${y(threshold)}" stroke="#b66516" stroke-dasharray="5 4"/><text x="590" y="${y(threshold)-5}" text-anchor="end" fill="#a86c2a" font-size="10">45°C trigger</text>`;
  for(const s of series){const points=s.points.map(p=>`${x(p[0]).toFixed(2)},${y(p[1]).toFixed(2)}`).join(' ');html+=`<polyline points="${points}" fill="none" stroke="${s.color}" stroke-width="2.3"/>`;}
  html+=`<line class="replay-cursor" x1="${x(replayTime)}" x2="${x(replayTime)}" y1="15" y2="185" stroke="#173e3b" stroke-width="1" opacity=".65"/></svg><div class="trace-legend">${series.map(s=>`<span><i class="method-dot" style="background:${s.color}"></i>${esc(s.label)}</span>`).join('')}</div>`;
  return html;
 }
 function drawReplayCharts(){
  const methods=['calibrated_feedback',replayData.baseline];
  const gainSeries=methods.map(method=>{
   const g=method==='legacy_guard'?1/.7:replayData.initial_gain,points=[[0,g]];
   if(method!=='legacy_guard')for(const o of replayData.traces[method].observations)if(o.applied){points.push([o.time_s,o.old_gain],[o.time_s,o.new_gain]);}
   points.push([40,gainAt(method,40)]);return{points,color:M[method].color,label:M[method].short};
  });
  $('gain-trace').innerHTML=lineChart(gainSeries,.45,2.05);
  const temp=methods.map(method=>({points:replayData.traces[method].states.map(s=>[s.time_s,s.temperature_c]),color:M[method].color,label:M[method].short}));
  const ymax=Math.max(47,...temp.flatMap(s=>s.points.map(p=>p[1]+1)));
  $('temperature-trace').innerHTML=lineChart(temp,24,ymax,45);
 }
 function setReplayTime(t){replayTime=Math.max(0,Math.min(40,t));renderReplayState();}
 function pauseReplay(){playing=false;$('play-replay').textContent='Play replay';lastFrame=0;}
 function tick(timestamp){
  if(!playing)return;
  if(!lastFrame)lastFrame=timestamp;
  const dt=Math.min(.1,(timestamp-lastFrame)/1000);lastFrame=timestamp;
  replayTime=Math.min(40,replayTime+dt*Number($('replay-speed').value));
  if(timestamp-paintTime>45||replayTime>=40){renderReplayState();paintTime=timestamp;}
  if(replayTime>=40){pauseReplay();return;}requestAnimationFrame(tick);
 }
 async function loadReplay(){
  if(!hasServer){showError('replay-error','The saved default replay works offline. Start the local Python server to generate a replay for other lab settings.');return;}
  if(busy){showError('replay-error','Wait for the current experiment to finish, then generate its replay.');return;}
  const button=$('load-replay');button.disabled=true;button.textContent='Generating Python replay…';showError('replay-error','');pauseReplay();
  try{replayData=await api('/api/replay',{...context(),seed:Number($('seed').value),baseline});replayData.saved=false;replayTime=0;renderReplay();toast('Replay generated and checked against the existing paper runner.');}
  catch(error){showError('replay-error',error.message);}
  finally{button.disabled=false;button.textContent='Generate replay from lab settings';}
 }
 function renderSampleJobs(){
  $('sample-jobs').innerHTML='<thead><tr><th>Arrival (ms)</th><th>Deadline (ms)</th><th>Actual work (work-ms)</th><th>Estimate (work-ms)</th><th>Estimate / actual</th></tr></thead><tbody>'+replayData.sample_jobs.map(j=>`<tr><td class="numeric">${fmt(j.arrival_ms,1)}</td><td class="numeric">${fmt(j.deadline_ms,1)}</td><td class="numeric">${fmt(j.actual_work_ms,3)}</td><td class="numeric">${fmt(j.estimate_ms,3)}</td><td class="numeric">${fmt(j.estimate_ms/j.actual_work_ms,3)}</td></tr>`).join('')+'</tbody>';
 }
 function renderMethods(){
  $('algorithm-cards').innerHTML=D.methods.map(m=>`<article class="card algorithm-card" style="--method-color:${m.color}"><h3>${esc(m.label)}</h3><span class="when">${esc(m.when)}</span><div class="algorithm-rule">${esc(m.rule)}</div><p>${esc(m.detail)}</p></article>`).join('');
  $('code-select').innerHTML=Object.entries(D.snippets).map(([id,s])=>`<option value="${id}">${esc(s.title)}</option>`).join('');
  $('code-select').addEventListener('change',renderCode);renderCode();renderSampleJobs();
 }
 function renderCode(){
  const s=D.snippets[$('code-select').value];$('code-title').textContent=s.title;$('code-explanation').textContent=s.explanation;
  $('code-path').textContent=`${s.path} · starts at line ${s.line}`;$('source-code').textContent=s.code;
  $('code-hash').textContent='Source SHA-256: '+s.sha256;
 }
 function calculateGain(apply=false){
  const old=Number($('calc-gain').value),estimate=Number($('calc-estimate').value),work=Number($('calc-work').value);
  if(!Number.isFinite(old)||!Number.isFinite(estimate)||!Number.isFinite(work)||old<.5||old>2||estimate<=0||work<=0){toast('Use a gain between 0.5 and 2 and positive work values.');return;}
  const ratio=work/estimate,value=Math.max(.5,Math.min(2,.8*old+.2*ratio));
  $('calc-result').textContent=fmt(value,3);$('calc-equation').textContent=`0.8 × ${fmt(old,3)} + 0.2 × (${fmt(work,1)} ÷ ${fmt(estimate,1)})`;
  $('calc-description').textContent=`The observed ratio is ${fmt(ratio,3)}. The corrected estimate becomes ${fmt(estimate*value,2)} work units. ${apply?'Press again to apply another identical completion.':'A Batch-20 rule waits for twenty new completed observations.'}`;
  if(apply)$('calc-gain').value=String(value);
 }
 function renderEvidence(){
  const family=Object.values(D.cases).flatMap(c=>c.family||[]);
  const pformat=p=>p<.001?Number(p).toExponential(2):fmt(p,3);
  $('family-table').innerHTML='<thead><tr><th>Profile</th><th>Shift</th><th>Endpoint</th><th>Lower / higher / tied</th><th>Holm-adjusted p</th></tr></thead><tbody>'+family.map(f=>`<tr><td>${f.profile==='apple_inspired'?'Apple-inspired':'Generic'}</td><td>${D.scenarios[f.scenario].short}</td><td>${f.endpoint==='estimated_j_per_task'?'Energy':'Miss rate'}</td><td class="numeric">${f.negative_n} / ${f.positive_n} / ${f.tied_n}</td><td class="numeric">${pformat(f.holm_p)}</td></tr>`).join('')+'</tbody>';
  $('posthoc-table').innerHTML='<thead><tr><th>Profile</th><th>Shift</th><th class="numeric">Energy difference (mJ/task)</th><th class="numeric">Miss difference (pp)</th><th class="numeric">Feedback joint wins / losses / other</th></tr></thead><tbody>'+D.provenance.publication.posthoc_effects.map(r=>`<tr><td>${r.profile==='apple_inspired'?'Apple-inspired':'Generic'}</td><td>${D.scenarios[r.scenario].short}</td><td class="numeric">${signed(r.estimated_j_per_task_delta_mean*1000,3)}</td><td class="numeric">${signed(r.deadline_miss_pct_delta_mean,3)}</td><td class="numeric">${r.joint_better} / ${r.joint_worse} / ${r.tradeoff_or_tie}</td></tr>`).join('')+'</tbody>';
  $('verification-cards').innerHTML=`<article class="card finding"><span class="eyebrow">MODEL, ANALYSIS & WEBSITE CHECKS</span><div class="number">72</div><p>The original paper audit ran 65 research checks and seven website integration checks. Includes shared history, correction timing, costs, compatibility and actual-run reconciliation.</p></article><article class="card finding"><span class="eyebrow">ORIGINAL FOLLOW-UP ROWS REPRODUCED</span><div class="number">6,240</div><p>Every original main and cost-sensitivity row rerun from unchanged source. All 240 contrasts and eight primary-family rows recompute.</p></article><article class="card finding warning"><span class="eyebrow">PHYSICAL VALIDATION</span><div class="number">Pending</div><p>No matched real-device power/runtime/temperature measurements or native controller deployment. Model checks do not calibrate hardware.</p></article>`;
  const docs=[
   ['PDF','Final research paper','Twelve-page IEEE manuscript with 6,790 words of main prose, 33 references, complete methods and the final equal-cost sensitivity.','../report_ieee/OS_Project_IEEE_Report_Periodic_Recalibration.pdf','Read the paper'],
   ['PPTX','Research presentation','The presentation accompanying the EDF scheduling study.','../presentation/OS_Research_Presentation.pptx','Download the slides'],
   ['CSV','Full fresh-cohort data','5,600 policy rows with seeds, measurements of the model and matching-input/source fingerprints.','/files/paper-data.csv','Download raw rows'],
   ['PLAN','Pre-run experiment plan','Fixed window sizes, primary Batch-20 comparator, eight endpoints, costs and reporting rules.','/files/experiment-plan.md','Read the plan'],
   ['CSV','All paired comparisons','Feedback versus all six comparators: mean effects, pointwise intervals, joint outcomes and zero-miss counts.','/files/paired-results.csv','Download paired data'],
  ];
  const offlineFiles={'/files/paper-data.csv':'../results/periodic/runs.csv','/files/paired-results.csv':'../results/periodic/paired.csv','/files/experiment-plan.md':'../revisions/2026-10-31/EXPERIMENT_AND_ANALYSIS_PLAN.md'};
  $('document-cards').innerHTML=docs.map(([kind,title,copy,url,label])=>{if(location.protocol==='file:'&&offlineFiles[url])url=offlineFiles[url];return `<article class="card document-card"><span class="document-icon">${kind}</span><div><h3>${title}</h3><p>${copy}</p><a href="${url}" target="_blank" rel="noopener">${label} ↗</a></div></article>`;}).join('');
  const settings=[['Execution','One preemptive serial worker; decisions every 10 ms; integration at 1 ms.'],['Capacity states','0.4 / 0.6 / 0.8 / 1.0 normalized service rates, not Mac clock percentages.'],['Power','Generic active power = 1 + 5s³ W; idle = 0.5 W; assumed E factor = 0.65.'],['Cooling','Ambient/initial 25°C; R = 6 or 18°C/W; C = 1.5 J/°C.'],['Thermal protection','Capacity capped at 0.4 from 45°C; released at 44°C. Illustrative, not device limits.'],['Shared calibration','20 historical completed tasks; mean work/estimate ratio clipped to 0.5–2.'],['Decision / transitions','Assumed 50 µs decision, 100 µs capacity change, 200 µs E/P change.'],['Learning cost','EWMA/rolling: 50 µs per completion. Batches: 10 µs observation + 40 µs per application.'],['Observation horizon','20 s arrivals; all tasks drain inside a common 40 s energy window.'],['Prediction errors','Synthetic e = b × actual work; a deployed real-task predictor is not supplied.']];
  $('model-settings').innerHTML='<div class="model-grid">'+settings.map(([a,b])=>`<div><strong>${a}</strong><span>${b}</span></div>`).join('')+'</div>';
 }
 function showTour(){
  const step=tourSteps[tourIndex];if(!step){endTour();return;}
  $('tour').hidden=false;document.body.classList.add('touring');$('tour-step').textContent=`GUIDED EXPLANATION · ${tourIndex+1} / ${tourSteps.length}`;
  $('tour-text').textContent=step[1];$('next-tour').textContent=tourIndex===tourSteps.length-1?'Finish guide':'Next step →';gotoView(step[0]);
 }
 function endTour(){tourIndex=-1;$('tour').hidden=true;document.body.classList.remove('touring');}
 async function checkServer(){
  if(location.protocol==='file:'){$('connection').textContent='Offline paper-data view';return;}
  try{const response=await api('/api/health');hasServer=response.available===true;}
  catch(_){hasServer=false;}
  $('connection').textContent=hasServer?'Python simulator connected':'Paper data available · Python server offline';$('connection').classList.toggle('online',hasServer);
 }
 document.addEventListener('click',event=>{const nav=event.target.closest('[data-view]');if(nav){event.preventDefault();gotoView(nav.dataset.view);}const modeButton=event.target.closest('[data-mode]');if(modeButton)setMode(modeButton.dataset.mode);});
 $('experiment-form').addEventListener('submit',runExperiment);$('export-results').addEventListener('click',downloadTable);
 $('load-replay').addEventListener('click',loadReplay);
 $('play-replay').addEventListener('click',()=>{if(playing)pauseReplay();else{if(replayTime>=40)setReplayTime(0);playing=true;lastFrame=0;$('play-replay').textContent='Pause replay';requestAnimationFrame(tick);}});
 $('reset-replay').addEventListener('click',()=>{pauseReplay();setReplayTime(0);});
 $('replay-slider').addEventListener('input',()=>{pauseReplay();setReplayTime(Number($('replay-slider').value));});
 $('jump-shift').addEventListener('click',()=>{pauseReplay();setReplayTime(10);});
 $('next-completion').addEventListener('click',()=>{pauseReplay();const next=replayData.traces.calibrated_feedback.observations.find(o=>o.time_s>replayTime+1e-8);if(next)setReplayTime(next.time_s);else toast('All tasks in this workload have completed.');});
 $('calculate-gain').addEventListener('click',()=>calculateGain(true));
 $('reset-calculator').addEventListener('click',()=>{$('calc-gain').value='.77';$('calc-estimate').value='21';$('calc-work').value='30';calculateGain(false);});
 ['calc-gain','calc-estimate','calc-work'].forEach(id=>$(id).addEventListener('change',()=>calculateGain(false)));
 $('copy-code').addEventListener('click',async()=>{try{await navigator.clipboard.writeText($('source-code').textContent);toast('Actual Python source copied.');}catch(_){const range=document.createRange();range.selectNodeContents($('source-code'));window.getSelection().removeAllRanges();window.getSelection().addRange(range);toast('Code selected. Use Copy to copy the snippet.');}});
 $('start-tour').addEventListener('click',()=>{tourIndex=0;showTour();});$('next-tour').addEventListener('click',()=>{tourIndex++;showTour();});$('end-tour').addEventListener('click',endTour);
 document.addEventListener('visibilitychange',()=>{if(document.hidden)pauseReplay();});
 history.scrollRestoration='manual';
 D.default_replay.saved=true;initControls();renderHome();renderMethods();renderEvidence();renderReplay();checkServer();gotoView(new URLSearchParams(location.hash.slice(1)).get('view')||location.hash.slice(1)||'home',true);
 window.CadenceDemo={getResult:()=>result,getReplay:()=>replayData,getReplayTime:()=>replayTime,gotoView};
})();
