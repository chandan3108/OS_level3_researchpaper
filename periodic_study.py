import math
from collections import deque
from dataclasses import dataclass, replace
from calibrated_study import (Settings as BaseSettings, ControlJob, Task,
    request_frequency, POLICIES, EXTRA_POLICIES, ESTIMATE_POLICIES)
from study import thermal_segment

CONTROLLERS = ('calibrated_static', 'calibrated_feedback', 'periodic_5',
               'periodic_20', 'periodic_50', 'rolling_20', 'legacy_guard')

@dataclass(frozen=True)
class Settings(BaseSettings):
    completion_observation_cost_s: float = .00001
    recalibration_application_cost_s: float = .00004

    def validate(self):
        super().validate()
        if not all(math.isfinite(x) and x>=0 for x in
                   (self.completion_observation_cost_s,self.recalibration_application_cost_s)):
            raise ValueError('recalibration costs must be finite and nonnegative')

class Correction:

    def __init__(self, controller, gain, history=()):
        self.controller=controller;self.gain=gain
        self.completed=self.updates=0;self.last_applied=False
        self.batch=[]
        self.window=deque((h['observed_work']/h['estimate'] for h in history),maxlen=20)
        if controller=='rolling_20' and len(self.window)!=20:
            raise ValueError('rolling baseline requires the common twenty-job history')

    def observe_completion(self, delivered, estimate, alpha, cap=2.):
        if not all(math.isfinite(v) and v>0 for v in (delivered,estimate)):
            raise ValueError('completion and estimate must be finite and positive')
        ratio=delivered/estimate;self.completed+=1;self.last_applied=False
        if self.controller=='calibrated_feedback':
            value=(1-alpha)*self.gain+alpha*ratio
        elif self.controller=='rolling_20':
            self.window.append(ratio);value=sum(self.window)/len(self.window)
        elif self.controller.startswith('periodic_'):
            self.batch.append(ratio)
            if len(self.batch)<int(self.controller.split('_')[1]):return
            value=sum(self.batch)/len(self.batch);self.batch.clear()
        else:
            raise ValueError('static correction must not receive online observations')
        self.gain=max(.5,min(cap,value)) if cap else max(.5,value)
        self.updates+=1;self.last_applied=True

    def completion_cost(self, settings):
        if self.controller.startswith('periodic_'):
            return settings.completion_observation_cost_s + self.last_applied*settings.recalibration_application_cost_s
        return settings.feedback_update_cost_s

def simulate(controller, tasks, settings, estimates=None, history=(), record_trace=False):
    if controller not in CONTROLLERS:
        raise ValueError('unknown correction controller')
    policy = 'guard' if controller in ('calibrated_static','legacy_guard') else 'feedback'
    settings = replace(settings, guard_gain=(1/.7 if controller=='legacy_guard' else settings.initial_gain))
    settings.validate()
    if policy not in POLICIES + EXTRA_POLICIES:
        raise ValueError('unknown policy')
    if not tasks:
        raise ValueError('empty tasks')
    if estimates is None:
        estimates = tuple(t.work*settings.estimate_ratio for t in tasks)
    if len(tasks) != len(estimates):
        raise ValueError('estimate count mismatch')
    pairs = sorted(zip(tasks, estimates), key=lambda p:p[0].arrival)
    for t,e in pairs:
        if not all(math.isfinite(v) for v in (t.arrival,t.deadline,t.work,e)) or t.arrival<0 or t.work<=0 or e<=0 or t.deadline<=t.arrival:
            raise ValueError('invalid task or estimate')
    ready, reservations, trace, latencies = [], [], [], []
    feedback = Correction(controller, settings.initial_gain, history)
    observations = []
    mode_switches = 0
    next_job = completed = missed = decisions = switches = overruns = 0
    energy = hot_time = protection_time = overhead_time = max_lateness = 0.0
    temperature = peak = settings.initial_c
    utilization = blocked_until = 0.0
    requested = last_frequency = 1.0 if policy == 'performance' else .4
    protection = False
    decision_ticks = round(settings.decision_s/settings.step_s)
    for tick in range(math.ceil(settings.horizon_s/settings.step_s)):
        now = tick*settings.step_s
        while next_job < len(pairs) and pairs[next_job][0].arrival <= now+1e-12:
            task, estimate = pairs[next_job]
            view = ControlJob(task.arrival,task.deadline,estimate)
            ready.append((task,view))
            reservations.append(view)
            next_job += 1
        ready.sort(key=lambda pair:pair[1].deadline)
        if ready and tick%decision_ticks == 0:
            reservations = [j for j in reservations if j.deadline>now]
            views = [j for _,j in ready]
            requested = request_frequency(views,reservations,now,settings,utilization,policy,feedback)
            if policy == 'deadline_thermal' and temperature >= settings.thermal_target_c:
                requested = min(requested,.6)
            if policy not in ('performance','fixed_low'):
                decisions += 1
                gain = feedback.gain if policy.startswith('feedback') else (settings.guard_gain if policy=='guard' else 1.)
                overruns += policy in ESTIMATE_POLICIES and any(gain*j.estimate-j.delivered<=1e-12 for j in views)
                blocked_until = max(blocked_until,now)+settings.decision_cost_s
        if settings.protection_enabled:
            if temperature >= settings.protection_c:
                protection = True
            elif temperature <= settings.protection_c-1:
                protection = False
        frequency = min(requested,.4) if protection else requested
        if ready and frequency != last_frequency:
            switches += 1
            mode_changed = bool(settings.apple_profile and ((frequency <= .4) != (last_frequency <= .4)))
            mode_switches += mode_changed
            blocked_until = max(blocked_until,now)+settings.switch_cost_s+mode_changed*settings.mode_switch_cost_s
            last_frequency = frequency

        busy_overhead = min(settings.step_s,max(0.0,blocked_until-now))
        cursor,service = busy_overhead,0.0
        overhead_time += busy_overhead
        while ready and cursor < settings.step_s-1e-12:
            task,view = ready[0]
            duration = min(settings.step_s-cursor,(task.work-view.delivered)/frequency)
            view.delivered += duration*frequency
            service += duration*frequency
            cursor += duration
            if view.delivered >= task.work-1e-12:
                finish = now+cursor
                latencies.append(finish-task.arrival)
                missed += finish>task.deadline+1e-9
                max_lateness = max(max_lateness,finish-task.deadline)
                completed += 1
                if policy.startswith('feedback'):
                    old_gain = feedback.gain
                    feedback.observe_completion(view.delivered,view.estimate,settings.feedback_alpha,settings.gain_cap)
                    if record_trace:
                        observations.append({'time_s':finish,'estimate_ms':view.estimate*1000,
                            'observed_work_ms':view.delivered*1000,'observed_ratio':view.delivered/view.estimate,
                            'old_gain':old_gain,'new_gain':feedback.gain,'applied':feedback.last_applied})
                    cost = feedback.completion_cost(settings)
                    used = min(cost,max(0.,settings.step_s-cursor))
                    cursor += used
                    overhead_time += used
                    blocked_until = max(blocked_until,now+cursor)+max(0.,cost-used)
                ready.pop(0)
        all_done = next_job==len(pairs) and not ready and blocked_until<=now+cursor+1e-12
        span = cursor if all_done else settings.step_s
        active_power = settings.active_static_w+settings.active_dynamic_w*frequency**3
        if settings.apple_profile and frequency <= .4:
            active_power *= settings.e_power_factor
        for power,duration in ((active_power,cursor),(settings.idle_w,max(0.0,span-cursor))):
            energy += power*duration
            temperature,hot = thermal_segment(temperature,power,duration,settings)
            hot_time += hot
            peak = max(peak,temperature)
        protection_time += span*protection
        utilization += (1-math.exp(-settings.step_s/.032))*(service/settings.step_s-utilization)
        if record_trace and (tick%20==0 or all_done):
            trace.append({'time_s':now+span,'temperature_c':temperature,'frequency_fraction':frequency if cursor else 0,
                          'queue_length':len(ready),'feedback_gain':feedback.gain,'energy_j':energy,'protection_active':int(protection),
                          'requested_capacity':requested,'execution_class':('E' if frequency<=.4 else 'P') if settings.apple_profile else 'single',
                          'overhead_time_s':overhead_time})
        if all_done:
            break
    if completed != len(tasks):
        raise RuntimeError('queue did not drain within the prespecified observation horizon')
    completion = now+span
    completion_energy = energy
    duration = max(0.0,settings.horizon_s-completion)
    end,hot = thermal_segment(temperature,settings.idle_w,duration,settings)
    energy += settings.idle_w*duration
    hot_time += hot
    peak = max(peak,end)
    latencies.sort()
    result = {'policy':policy,'tasks':completed,'on_time_tasks':completed-missed,
              'completion_time_s':completion,'horizon_s':settings.horizon_s,
              'energy_to_completion_j':completion_energy,'estimated_energy_j':energy,
              'estimated_j_per_task':energy/completed,
              'estimated_j_per_ontime_task':energy/(completed-missed) if completed>missed else None,
              'deadline_miss_pct':100*missed/completed,
              'p95_latency_ms':latencies[math.ceil(.95*completed)-1]*1000,
              'max_lateness_ms':max_lateness*1000,'estimated_peak_c':peak,
              'time_above_target_s':hot_time,'protection_time_s':protection_time,
              'controller_decisions':decisions,'frequency_switches':switches,
              'overrun_decisions':overruns,'overhead_time_s':overhead_time,
              'feedback_gain_final':feedback.gain,'feedback_completions':feedback.completed,
              'mode_switches':mode_switches,'profile_id':int(settings.apple_profile),
              'correction_updates':feedback.updates,'controller':controller}
    if record_trace:result['completion_observations']=observations
    return result,trace
