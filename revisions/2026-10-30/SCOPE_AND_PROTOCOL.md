# 30 October 2026: scope and protocol recorded before new results

Revised question: Under changing workloads, does completion-based runtime correction reduce modeled energy while meeting a declared deadline requirement, compared with a static correction calibrated from the same historical data?

Authorized work: two detailed research PDFs; a clearer demonstrable simulation; a bounded Apple Silicon-inspired serial E/P execution abstraction; updates to the existing IEEE paper. Native processor benchmarks, power sampling, physical stress tests, kernel changes and hardware-control calls remain on hold.

The old generic engines and raw datasets are frozen. New results belong in results/calibrated/. A new engine is a documented derivative of review_study.py; gain initialization, an explicit architecture profile, synthetic control costs and limited trace logging are the only new mechanism families. EDF-prefix demand, discrete capacity choices, recovery, common thermal protection, completion feedback and fixed-window accounting remain.

Fair calibration: 20 completed historical jobs, independent per seed; observed work/initial-estimate ratios determine the same clipped initial gain for both static and online methods. Static correction may shrink estimates, just as feedback can. Calibration jobs finish before the evaluated release window; their common collection cost is outside the evaluation and is declared, never attributed as free measurement in deployment. Calibration ratios are synthetic observations, not hardware measurements. No test observations choose the static multiplier or tune alpha/caps.

Workload designs: stationary 30% overestimate; overestimate-to-underestimate shift; accurate-to-underestimate shift; noisy estimates; per-input-family mixture that challenges a shared gain. Same task and estimate hashes within each comparison. Primary contrast: feedback cap 2 versus calibrated static. Other references: uncorrected and legacy fixed guard 1/0.7. Learning rate remains .2; clipping remains .5–2. Primary power/cooling parameters are unchanged.

Profiles: generic single CPU retains the original service/power model. Apple-inspired serial worker uses normalized E/P effective-capacity states and an assumed E-mode power reduction plus mode transition cost; it is neither XNU emulation nor an M-series calibration. Its assumptions are explicit and changed one at a time in sensitivity checks. No real QoS-to-frequency mapping or Apple temperature limit is claimed.

Both bursty and Poisson arrival patterns; ordinary/restricted synthetic cooling; seeds 100–119 for evaluation; 20 s release and 40 s energy horizon; zero versus nonzero synthetic control/transition overhead. All jobs must drain. 20 paired seeds per condition; the policy count is not independent sample size. New comparisons are exploratory, report all conditions and losses, paired mean differences and percentile bootstrap intervals, plus joint better/worse/trade-off counts. No numerical target is required to pass.

Validation layers: internal checks and reruns can be completed now; literature consistency and platform mapping can be audited now; public benchmark code is a candidate future workload, not measured validation data; physical/device validation remains unperformed. Novelty conclusions are bounded by the screened literature and do not assert universal priority.
