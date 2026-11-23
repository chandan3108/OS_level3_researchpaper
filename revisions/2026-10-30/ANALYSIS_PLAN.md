# Explicit pre-analysis decision rules

Recorded before opening the completed new sweep or its paired summaries. This is a project analysis plan, not an external preregistration. Questions were motivated by the older results.

All 80 profile/cooling/cost/arrival/scenario conditions are retained. Primary target is calibrated_feedback and primary baseline is calibrated_static. Each condition has 20 independent seeded workload streams reused across policies. An observed strict energy/deadline improvement requires lower energy and no increase in miss percentage in that seed. Joint worse is the reverse; other cases are trade-offs or joint ties. Mean differences are also shown. This is an empirical comparison, not a proof of population noninferiority or deadline guarantees. The absolute zero-observed-miss subset is separately flagged.

Variable paired differences receive 5,000-resample pointwise percentile bootstrap intervals. Exact constants are descriptive and have blank intervals. No p-value selection or omnibus victory count is used. No multiplicity-adjusted significance or causal hardware claim is made. The run-level max is a finite-sample worst case, not a certified bound. All conditions and all negative findings must be reported, including cases where shared calibration removes the old energy advantage.

Architecture sensitivity changes E-mode power factor only, holding identical tasks and estimates. It investigates assumptions, not Apple parameter calibration. Native hardware validation remains on hold.
