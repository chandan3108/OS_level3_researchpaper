# Completion Feedback versus Periodic Recalibration

An EDF Study with an Apple-Silicon-Inspired Model  
Chandan N and Dhruv · PES University

## Abstract

We asked whether updating a runtime-estimate correction after every completion was worth its control cost. We tested exponential smoothing against nonoverlapping batches and a rolling window. Each history-based method started from the same completed history. We held EDF execution and thermal control fixed, so each comparison used the same capacity-selection rule. We ran seven controllers in 5,600 synthetic policy evaluations. All energy values came from simulation, with no measured Apple savings or hard real-time guarantee. Under ordinary cooling and bursty arrivals in our Apple-inspired serial model, feedback reduced high-to-low-shift energy by 0.694% and misses by 0.322 percentage points against twenty-task recalibration. Accurate-to-low traded lower energy for slightly more misses. Batch 5 used less mean energy in both shifts under original costs, zero costs and a separate post-hoc equal-completion-cost check. We found mixed-Poisson losses and checked that the tested Poisson workloads could not meet every deadline at maximum capacity. We reproduced the original follow-up rows.

## Run the website demo

With Python 3.13, from the repository root:

~~~sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python website/serve.py --open
~~~

Open http://127.0.0.1:8841 to explore the paper data or run a new software simulation. For the saved data and replay only, open [website/index.html](website/index.html) directly.

## Reproduce the paper results

~~~sh
python -m unittest discover
python reproduce.py
~~~

The second command runs the historical calibration cohort and the fresh periodic-recalibration cohort, both cost sensitivities, the feasibility checks and the post-hoc Batch 5 comparison. It verifies the result files against the paper's saved numerical outputs, regenerates the figures and tables in `report_ieee/` and rebuilds the website snapshot. The bundled demo uses the saved paper data immediately.

[IEEE research paper (PDF)](report_ieee/OS_Project_IEEE_Report_Periodic_Recalibration.pdf) · [Research presentation (PowerPoint)](presentation/OS_Research_Presentation.pptx)
