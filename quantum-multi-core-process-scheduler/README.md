# Quantum Multi-Core Process Scheduler

A hybrid classical-quantum academic prototype that uses **QUBO** and **QAOA** to optimize process-to-core assignment, then evaluates scheduling policies on each core.

> **Status:** Simulation-based prototype. QAOA runs with Qiskit's local `StatevectorSampler`; this project does not submit jobs to quantum hardware.

## What it does

1. Accepts process count, CPU core count, arrival time (AT), burst time (BT), priority, and Round Robin quantum.
2. Calculates single-queue baselines for FCFS, SJF, Priority, and Round Robin.
3. Builds a QUBO model for assigning each process to one CPU core.
4. Runs QAOA using COBYLA and a local statevector simulator.
5. Selects a scheduling policy for each core using classical post-processing.
6. Reports waiting time, turnaround time, response time, load imbalance, CPU utilization, and context switches.

**Important distinction:** QAOA optimizes process-to-core assignment. The choice of FCFS/SJF/Priority/Round Robin for each core is classical post-processing in this implementation.

## QUBO formulation

For process `i` and core `c`, binary variable `x[i,c]` is 1 when process `i` is assigned to core `c`, otherwise 0.

With `N` processes and `K` cores, the model has `N × K` binary variables.

### Assignment penalty

Each process must be assigned to exactly one core:

\[
\sum_{c=1}^{K}x_{i,c}=1
\]

The model penalizes violations:

\[
C_{\mathrm{assignment}} =
A\sum_{i=1}^{N}\left(1-\sum_{c=1}^{K}x_{i,c}\right)^2
\]

### Workload balance

The total burst-time load of core `c` is:

\[
L_c=\sum_{i=1}^{N}BT_i x_{i,c}
\]

The target average load is:

\[
\bar L=\frac{\sum_i BT_i}{K}
\]

The balance objective is:

\[
C_{\mathrm{balance}} =
B\sum_{c=1}^{K}(L_c-\bar L)^2
\]

The full objective is:

\[
\min E(x)=C_{\mathrm{assignment}}+C_{\mathrm{balance}}
\]

The implementation includes the constant terms in the `QuadraticProgram`. The previous version omitted those constants: this did not change which assignment minimizes the objective, but it shifted the displayed score. The updated code reports the full objective.

### What does the QUBO value represent?

It is a mathematical cost score for an assignment—not CPU time, waiting time, or core load. Lower values are preferred. The objective combines workload imbalance and assignment-rule penalties. A zero score corresponds to a valid assignment with perfectly balanced burst-time loads under this simplified model.

## QAOA workflow

- Convert the QUBO into a binary optimization problem.
- Use QAOA to create and sample candidate bitstrings.
- Use COBYLA as the classical optimizer for QAOA parameters.
- Decode the selected bitstring into process-to-core assignments.

QAOA is approximate and does not guarantee a global optimum on every run.

## Architecture

```text
User input (AT, BT, Priority, core count, RR quantum)
                 |
       +---------+----------+
       |                    |
       v                    v
Classical baselines     QUBO formulation
FCFS / SJF / Priority   Binary assignment variables
/ Round Robin           Penalty + load-balancing cost
       |                    |
       |                    v
       |                QAOA + COBYLA
       |                StatevectorSampler
       |                    |
       +---------+----------+
                 |
                 v
       Classical policy selection
          for each CPU core
                 |
                 v
       Final metrics and timelines
```

## Requirements

- Python **3.10–3.12** recommended.
- Qiskit 1.2.4
- Qiskit Algorithms 0.3.1
- Qiskit Optimization 0.6.1
- SciPy

The local statevector simulator means no IBM Quantum account or quantum hardware is required.

## Installation

### Windows PowerShell

```powershell
git clone https://github.com/<your-username>/quantum-multi-core-process-scheduler.git
cd quantum-multi-core-process-scheduler
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python src/scheduler.py
```

### macOS / Linux

```bash
git clone https://github.com/<your-username>/quantum-multi-core-process-scheduler.git
cd quantum-multi-core-process-scheduler
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python src/scheduler.py
```

## Example input

```text
Processes: 3
CPU Cores: 2
Round Robin time quantum: 2

P1: AT=0, BT=6, Priority=2
P2: AT=1, BT=2, Priority=1
P3: AT=2, BT=4, Priority=3
```

The exact QAOA assignment and objective can vary by run and software version. Example inputs are illustrative, not guaranteed outputs.

## Output metrics

| Metric | Meaning |
|---|---|
| Average Waiting Time | Average time spent waiting in the ready queue |
| Average Turnaround Time | Completion time minus arrival time, averaged |
| Average Response Time | First CPU start time minus arrival time, averaged |
| Load Imbalance | Maximum core burst-time load minus minimum core burst-time load |
| CPU Utilization | Aggregate busy time divided by core count × makespan |
| Context Switches | Process changes between adjacent segments on each core |
| QUBO Objective | Mathematical cost of the process-to-core assignment |

## Assumptions and limitations

- The QUBO objective currently balances total burst time. It does **not** directly minimize waiting time, turnaround time, or response time.
- Arrival time and priority affect the scheduling simulations but are not currently included in the QUBO allocation objective.
- FCFS, SJF, and Priority are non-preemptive. A smaller priority number means higher priority.
- Round Robin is preemptive and uses the supplied time quantum.
- The classical baseline report runs each algorithm on the full process set as a single queue. The final multi-core evaluation simulates each core's assigned process group separately.
- Per-core scheduling-policy selection is classical post-processing, not QAOA.
- This is an educational prototype, not a production operating-system scheduler.
- Statevector simulation scales exponentially with qubit count and can become slow or memory-intensive.
- QAOA is approximate and does not guarantee a global optimum.
- Process dependencies, I/O blocking, deadlines, migrations, cache affinity, and heterogeneous CPU cores are not modeled.

## Repository structure

```text
quantum-multi-core-process-scheduler/
├── README.md
├── requirements.txt
├── .gitignore
├── LICENSE
└── src/
    ├── __init__.py
    └── scheduler.py
```

## Future work

- Include waiting-time or makespan terms in the QUBO objective.
- Compare QAOA with exact brute-force solutions on small instances.
- Run multiple seeds and report average solution quality.
- Make QAOA depth and optimizer settings configurable.
- Add Gantt-chart visualization and workload plots.
- Evaluate on a real quantum backend when access is available.

## License

MIT License. See [LICENSE](LICENSE).

## Author

**Your Name** — VIT Vellore

Replace this placeholder with your GitHub profile and project details before publishing.
