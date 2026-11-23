# Periodic-recalibration follow-up — 31 October 2026

Written before executing or inspecting the fresh-seed follow-up. Questions are informed by the previous data and reviewer criticism; this is a local prospective follow-up plan, not external preregistration. All native benchmarks, stress tests, physical power sampling and hardware control remain ON HOLD.

## Question and comparison
Does completion-by-completion EWMA correction improve modeled energy and deadline outcomes relative to periodic or windowed recalibration using the same completed observations? The old frozen-static comparison remains descriptive context, not sufficient evidence that EWMA is the best adaptive method.

Preserve the 30 October engine and all saved data. A separate derivative retains EDF, demand margin, capacity states, recovery, thermal arbitration, energy window, alpha .2 and clipping [.5,2]. Only the correction strategy and its declared modeled costs change. Current old seeds 100–119 are not reused as fresh evidence. New evaluation and calibration histories use seeds 200–219.

## Controllers and fixed choices
All methods receive the same 20 completed calibration jobs and initial clipped mean work/estimate ratio.
- calibrated_static freezes that initial value.
- calibrated_feedback applies .8*old+.2*new_ratio at every completion.
- periodic_5, periodic_20 and periodic_50 collect nonoverlapping batches of 5, 20 or 50 new completed ratios, replace the gain with the clipped batch mean, and hold it between batches. An incomplete last batch does not update. Batch boundaries count completions, not arrivals or time; no shift alarm or future work is available.
- rolling_20 starts with the same twenty calibration ratios and replaces the oldest ratio at every completion; gain is the clipped mean of the latest twenty ratios.
- legacy_guard retains gain 1/.7.

Primary engineering comparator is periodic_20, chosen to match the initial calibration sample size, not selected from follow-up outcomes. Other batch sizes and rolling_20 are labeled sensitivity/exploratory alternatives; all are reported, with no best-policy relabeling.

## Costs and design
The same 50 us decision, 100 us capacity-change and 200 us E/P-change costs remain. EWMA and rolling updates cost 50 us per completed observation. Periodic strategies charge 10 us for each observation/accumulation and an additional 40 us when applying a batch correction. These unmeasured assumptions explicitly favor less frequent application. A focused sensitivity charges periodic_20 the full 50 us at every completion (50 us observation, 0 extra application), removing that cost advantage. Calibration collection cost remains common and outside the evaluation window.

Main follow-up: 2 profiles x 2 cooling settings x 2 arrival patterns x 5 estimation scenarios x 20 seeds x 7 controllers = 5,600 policy evaluations in 800 matched groups / 40 conditions, all with modeled costs. A zero-cost sensitivity repeats the two shifts with ordinary cooling and bursty arrivals for both profiles: 4 conditions x 20 x 7 = 560 evaluations. The equal-completion-cost sensitivity repeats periodic_20 in those four modeled-cost conditions: 80 additional evaluations; matched EWMA references are reused explicitly, not counted as new independent samples.

The workloads, calibration generator and default Apple-inspired factor .65 stay unchanged. Apple profile remains a serial E/P abstraction with assumed parameters, not a physical device model. No constants are fitted to outcome targets.

## Focused statistical family
Primary family: EWMA minus periodic_20 for the two shift scenarios (high_to_low, accurate_to_low), both profiles, ordinary cooling, bursty arrivals, modeled costs: four conditions and two endpoints (J/task and deadline-miss percentage), hence EIGHT tests. Lower favors EWMA. Exact one-sided sign tests test directional consistency among non-tied seed pairs (negative probability at most .5 conditional on a non-tie); ties are excluded from the binomial denominator and all positive/negative/tie counts are reported. All-tied endpoints receive p=1 and zero effective non-tied n. Holm correction covers all eight tests together at .05. This tests directions, not the magnitude of mean effects, equivalence or deadline noninferiority. No family is chosen after viewing new outcomes.

Report paired mean effects with 5,000-resample pointwise bootstrap intervals, joint better/worse/trade-off-or-tie counts, strict-energy joint improvements, and both policies' zero-observed-miss run counts. Constant rows remain descriptive with no fabricated [0,0] uncertainty. Energy and miss tests are separate; a joint superiority/noninferiority claim cannot be inferred merely from one significant endpoint. All comparisons outside the fixed family remain exploratory. Preserve unfavorable results and do not substitute a different primary comparator if periodic_20 wins.

## Feasibility and reporting
Recheck unconstrained maximum-capacity EDF on every actual task stream for seeds 100–119 and 200–219, both arrival patterns, no thermal cap and zero overhead (80 diagnostic streams). Cross-check an independent event-driven EDF calculation with the simulation engine. Report only whether zero misses are feasible under this serial preemptive model; do not claim that the maximum-speed retained-job miss count is a lower bound on the number of misses for every policy. Separate unavoidable zero-miss infeasibility from additional controller misses.

Update the paper with the fresh comparison, the legacy-guard loop, current Poisson mixed losses and feasibility context, an explicit H1–H4 evidence table, zero-miss counts, and readable paired-effect figures with pointwise intervals. Add the unclipped mean reciprocal-noise value exp(.25^2)=1.06449, acknowledging finite history and clipping. Keep physical validity pending. The prior 80-condition sweep and its 240 exploratory contrasts remain unchanged and versioned.
