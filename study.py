import math
import random
from dataclasses import dataclass

SPEEDS = (0.4, 0.6, 0.8, 1.0)
POLICIES = ("performance", "fixed_low", "reactive", "deadline", "deadline_thermal")
ADAPTIVE = ("deadline", "deadline_thermal")


@dataclass(frozen=True)
class Settings:
    seconds: float = 20.0
    step_s: float = 0.001
    decision_s: float = 0.010
    estimate_ratio: float = 1.0
    margin: float = 0.10
    ambient_c: float = 25.0
    initial_c: float = 25.0
    resistance_c_per_w: float = 6.0
    capacitance_j_per_c: float = 1.5
    thermal_target_c: float = 40.0
    protection_c: float = 45.0
    decision_cost_s: float = 0.0
    switch_cost_s: float = 0.0

    def validate(self):
        for name, value in self.__dict__.items():
            if not math.isfinite(value):
                raise ValueError(f"{name} must be finite")
        for name in ("seconds", "step_s", "decision_s", "estimate_ratio",
                     "resistance_c_per_w", "capacitance_j_per_c"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")
        for name in ("margin", "decision_cost_s", "switch_cost_s"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be nonnegative")
        if self.decision_s < self.step_s or self.decision_cost_s >= self.decision_s:
            raise ValueError("decision interval must cover a step and exceed decision cost")
        if self.protection_c <= self.thermal_target_c:
            raise ValueError("protection threshold must exceed the thermal target")
        if not math.isclose(self.decision_s / self.step_s,
                            round(self.decision_s / self.step_s), abs_tol=1e-8):
            raise ValueError("decision interval must be an integer multiple of the step")


@dataclass(frozen=True)
class Task:
    arrival: float
    deadline: float
    work: float


@dataclass
class Pending:
    task: Task
    estimate: float
    executed: float = 0.0

    @property
    def estimated_left(self):
        return max(0.0, self.estimate - self.executed)


def make_workload(seed, pattern, seconds):
    if pattern not in ("steady", "bursty"):
        raise ValueError("unknown workload pattern")
    rng = random.Random(seed)
    jobs, millis = [], 0
    while millis / 1000 < seconds:
        arrival = millis / 1000
        jobs.append(Task(arrival, arrival + 0.100, rng.uniform(0.018, 0.030)))
        millis += 30 if pattern == "bursty" and (millis // 1000) % 2 else 60
    return tuple(jobs)


def select_frequency(ready, now, settings, utilization, policy):

    if policy == "performance":
        return 1.0
    if policy == "fixed_low":
        return 0.4
    if policy == "reactive":
        required = utilization * 1.25
    else:

        if any(job.estimated_left <= 1e-12 or job.task.deadline <= now for job in ready):
            return 1.0
        work, required = 0.0, 0.0
        for job in ready:
            work += job.estimated_left
            required = max(required, work / max(settings.step_s, job.task.deadline - now))
        required *= 1 + settings.margin
    return next((f for f in SPEEDS if f >= required), 1.0)


def thermal_segment(temperature, power, duration, settings):

    if duration <= 0:
        return temperature, 0.0
    tau = settings.resistance_c_per_w * settings.capacitance_j_per_c
    equilibrium = settings.ambient_c + power * settings.resistance_c_per_w
    end = equilibrium + (temperature - equilibrium) * math.exp(-duration / tau)
    threshold = settings.thermal_target_c
    if min(temperature, end) >= threshold:
        hot = duration
    elif max(temperature, end) <= threshold:
        hot = 0.0
    else:
        crossing = -tau * math.log((threshold - equilibrium) / (temperature - equilibrium))
        hot = crossing if temperature > threshold else duration - crossing
    return end, min(duration, max(0.0, hot))


def simulate(policy, tasks, settings, record_trace=False):
    settings.validate()
    if policy not in POLICIES:
        raise ValueError("unknown policy")
    if not tasks or any(t.work <= 0 or t.arrival < 0 or t.deadline <= t.arrival
                        or not all(math.isfinite(v) for v in (t.work, t.arrival, t.deadline))
                        for t in tasks):
        raise ValueError("tasks must be nonempty, finite, positive work with valid times")
    tasks = sorted(tasks, key=lambda t: t.arrival)
    ready, latencies, trace = [], [], []
    next_job = completed = missed = decisions = switches = overruns = 0
    now, energy, hot_time, overhead_time = 0.0, 0.0, 0.0, 0.0
    temperature = peak = settings.initial_c
    utilization, blocked_until = 0.0, 0.0
    requested = 1.0 if policy == "performance" else 0.4
    last_frequency, protection = requested, False
    decision_ticks = round(settings.decision_s / settings.step_s)

    limit = tasks[-1].arrival + sum(t.work for t in tasks) / 0.4 * 10 + 10
    for tick in range(math.ceil(limit / settings.step_s)):
        now = tick * settings.step_s
        while next_job < len(tasks) and tasks[next_job].arrival <= now + 1e-12:
            task = tasks[next_job]
            ready.append(Pending(task, task.work * settings.estimate_ratio))
            next_job += 1
        ready.sort(key=lambda job: job.task.deadline)
        if ready and tick % decision_ticks == 0:
            requested = select_frequency(ready, now, settings, utilization, policy)
            if policy == "deadline_thermal" and temperature >= settings.thermal_target_c:
                requested = min(requested, 0.6)
            if policy not in ("performance", "fixed_low"):
                decisions += 1
                if policy in ADAPTIVE and any(j.estimated_left <= 1e-12 for j in ready):
                    overruns += 1
                blocked_until = max(blocked_until, now) + settings.decision_cost_s
        if temperature >= settings.protection_c:
            protection = True
        elif temperature <= settings.protection_c - 1.0:
            protection = False
        frequency = min(requested, 0.4) if protection else requested
        if ready and frequency != last_frequency:
            switches += 1
            blocked_until = max(blocked_until, now) + settings.switch_cost_s
            last_frequency = frequency
        busy_overhead = min(settings.step_s, max(0.0, blocked_until - now)) if ready else 0.0
        overhead_time += busy_overhead
        cursor = busy_overhead
        service = 0.0
        while ready and cursor < settings.step_s - 1e-12:
            job = ready[0]
            remaining = job.task.work - job.executed
            duration = min(settings.step_s - cursor, remaining / frequency)
            job.executed += duration * frequency
            service += duration * frequency
            cursor += duration
            if job.executed >= job.task.work - 1e-12:
                finish = now + cursor
                latencies.append(finish - job.task.arrival)
                missed += finish > job.task.deadline + 1e-9
                completed += 1
                ready.pop(0)
        all_done = next_job == len(tasks) and not ready
        span = cursor if all_done else settings.step_s
        active_time = cursor
        idle_time = max(0.0, span - active_time)
        active_power = 1.0 + 5.0 * frequency ** 3
        for power, duration in ((active_power, active_time), (0.5, idle_time)):
            energy += power * duration
            temperature, hot = thermal_segment(temperature, power, duration, settings)
            hot_time += hot
            peak = max(peak, temperature)
        alpha = 1 - math.exp(-settings.step_s / 0.032)
        utilization += alpha * (service / settings.step_s - utilization)
        if record_trace and (tick % 20 == 0 or all_done):
            trace.append({"time_s": now + span, "frequency_fraction": frequency if active_time else 0,
                          "temperature_c": temperature, "queue_length": len(ready),
                          "energy_j": energy, "protection_active": int(protection)})
        if all_done:
            break
    if completed != len(tasks):
        raise RuntimeError("Run did not drain; reduce overhead or inspect model settings")
    latencies.sort()
    return {"policy": policy, "estimate_ratio": settings.estimate_ratio if policy in ADAPTIVE else "NA",
            "tasks": completed, "on_time_tasks": completed - missed,
            "completion_time_s": now + span, "horizon_s": now + span,
            "energy_to_completion_j": energy, "estimated_energy_j": energy,
            "estimated_j_per_task": energy / completed,
            "estimated_j_per_ontime_task": energy / (completed - missed) if completed > missed else None,
            "p95_latency_ms": latencies[math.ceil(0.95 * completed) - 1] * 1000,
            "deadline_miss_pct": 100 * missed / completed,
            "estimated_peak_c": peak, "time_above_target_s": hot_time,
            "final_temperature_c": temperature, "controller_decisions": decisions,
            "frequency_switches": switches, "overrun_decisions": overruns,
            "overhead_time_s": overhead_time}, trace


def pad_to_horizon(result, trace, horizon, settings):

    duration = horizon - result["horizon_s"]
    if duration < -1e-9:
        raise ValueError("horizon cannot precede completion")
    end, hot = thermal_segment(result["final_temperature_c"], 0.5, max(0, duration), settings)
    result["estimated_energy_j"] += max(0, duration) * 0.5
    result["horizon_s"] = horizon
    result["time_above_target_s"] += hot
    result["estimated_peak_c"] = max(result["estimated_peak_c"], end)
    result["final_temperature_c"] = end
    result["estimated_j_per_task"] = result["estimated_energy_j"] / result["tasks"]
    result["estimated_j_per_ontime_task"] = (result["estimated_energy_j"] / result["on_time_tasks"]
                                             if result["on_time_tasks"] else None)
    if trace and duration > 1e-9:
        trace.append({"time_s": horizon, "frequency_fraction": 0, "temperature_c": end,
                      "queue_length": 0, "energy_j": result["estimated_energy_j"], "protection_active": 0})
