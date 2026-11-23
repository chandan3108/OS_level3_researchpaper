import math
import random
from dataclasses import dataclass
from study import Settings as OriginalSettings, Task, thermal_segment

SPEEDS = (0.4, 0.6, 0.8, 1.0)
POLICIES = ('performance', 'fixed_low', 'reactive', 'deadline',
            'deadline_thermal', 'avr', 'feedback', 'guard')
EXTRA_POLICIES = ('feedback_no_recovery', 'deadline_no_recovery')
ESTIMATE_POLICIES = POLICIES[3:] + EXTRA_POLICIES


@dataclass(frozen=True)
class Settings(OriginalSettings):
    active_static_w: float = 1.0
    active_dynamic_w: float = 5.0
    idle_w: float = 0.5
    feedback_alpha: float = 0.2
    protection_enabled: bool = True
    horizon_s: float = 40.0
    gain_cap: float = 2.0
    guard_gain: float = 1/0.7
    initial_gain: float = 1.0
    apple_profile: float = 0.0
    e_power_factor: float = 0.65
    mode_switch_cost_s: float = 0.0
    feedback_update_cost_s: float = 0.0

    def validate(self):
        super().validate()
        if min(self.active_static_w, self.active_dynamic_w, self.idle_w) < 0:
            raise ValueError('power components must be nonnegative')
        if not 0 <= self.feedback_alpha <= 1:
            raise ValueError('feedback alpha must be in [0, 1]')
        if self.horizon_s <= self.seconds:
            raise ValueError('observation horizon must exceed release window')
        if self.gain_cap != 0 and self.gain_cap < 1:
            raise ValueError('gain cap must be zero (uncapped) or at least one')
        if self.guard_gain <= 0:
            raise ValueError('guard gain must be positive')
        if self.initial_gain < .5 or (self.gain_cap and self.initial_gain > self.gain_cap):
            raise ValueError('initial gain must be within the clipping range')
        if self.apple_profile not in (0, 1) or not 0 < self.e_power_factor <= 1:
            raise ValueError('invalid abstract execution profile')
        if min(self.mode_switch_cost_s,self.feedback_update_cost_s) < 0:
            raise ValueError('synthetic costs must be nonnegative')


@dataclass
class ControlJob:
    arrival: float
    deadline: float
    estimate: float
    delivered: float = 0.0


@dataclass
class Feedback:
    gain: float = 1.0
    completed: int = 0

    def observe_completion(self, delivered, estimate, alpha, cap=2.0):

        if delivered <= 0 or estimate <= 0:
            raise ValueError('completion and estimate must be positive')
        value = max(0.5, (1-alpha)*self.gain + alpha*delivered/estimate)
        self.gain = min(cap,value) if cap else value
        self.completed += 1


def request_frequency(ready, reservations, now, settings, utilization, policy, feedback):

    if policy == 'performance':
        return 1.0
    if policy == 'fixed_low':
        return 0.4
    if policy == 'reactive':
        required = 1.25 * utilization
    else:
        gain = feedback.gain if policy.startswith('feedback') else (settings.guard_gain if policy == 'guard' else 1.0)
        remaining = [max(0.0, gain*j.estimate - j.delivered) for j in ready]
        recovery = not policy.endswith('no_recovery')
        if recovery and any(r <= 1e-12 or j.deadline <= now for r,j in zip(remaining, ready)):
            return 1.0
        if policy == 'avr':

            required = sum(j.estimate/(j.deadline-j.arrival)
                           for j in reservations if j.arrival <= now < j.deadline)
        else:
            work = required = 0.0
            for job, left in zip(ready, remaining):
                work += left
                required = max(required, work/max(settings.step_s, job.deadline-now))
            required *= 1 + settings.margin
    return next((f for f in SPEEDS if f >= required), 1.0)


def make_case(seed, pattern, error, seconds=20.0):

    rng, erng = random.Random(seed), random.Random(100000+seed)
    tasks, estimates = [], []
    arrival = 0.0
    while arrival < seconds-1e-12:
        if pattern == 'poisson':
            work = rng.uniform(0.010, 0.018) if rng.random() < .7 else rng.uniform(.035,.055)
            relative = rng.choice((.080,.100,.150))
        else:
            work, relative = rng.uniform(.018,.030), .100
        task = Task(arrival, arrival+relative, work)
        tasks.append(task)
        if error in ('noise','heavy_noise'):

            sigma = .25 if error == 'noise' else .75
            ratio = erng.lognormvariate(-sigma**2/2, sigma)
        elif error == 'drift':
            ratio = 1.0 if arrival < seconds/2 else .7
        else:
            ratio = float(error)
        estimates.append(work*ratio)
        if pattern in ('steady','bursty','burst_first'):
            millis = round(arrival*1000)
            burst = ((pattern == 'bursty' and (millis//1000)%2) or
                     (pattern == 'burst_first' and not (millis//1000)%2))
            arrival = (millis + (30 if burst else 60))/1000
        elif pattern == 'poisson':

            arrival += max(.001, round(rng.expovariate(25.0),3))
        else:
            raise ValueError('unknown workload')
    return tuple(tasks), tuple(estimates)


def simulate(policy, tasks, settings, estimates=None, record_trace=False):
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
    feedback = Feedback(gain=settings.initial_gain)
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
                            'old_gain':old_gain,'new_gain':feedback.gain})
                    cost = settings.feedback_update_cost_s
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
              'mode_switches':mode_switches,'profile_id':int(settings.apple_profile)}
    if record_trace:result['completion_observations']=observations
    return result,trace
