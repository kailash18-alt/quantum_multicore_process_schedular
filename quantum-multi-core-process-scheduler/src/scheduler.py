"""Quantum Multi-Core Process Scheduler: formal QUBO + QAOA via Qiskit.
Local StatevectorSampler simulates the quantum circuit; no hardware required.
QAOA optimizes process-to-core assignment. Per-core policy choice is classical.
Install: python -m pip install qiskit qiskit-algorithms qiskit-optimization
"""
from dataclasses import dataclass
from itertools import product
import sys

try:
    from qiskit.primitives import StatevectorSampler
    from qiskit_algorithms import QAOA
    from qiskit_algorithms.optimizers import COBYLA
    from qiskit_optimization import QuadraticProgram
    from qiskit_optimization.algorithms import MinimumEigenOptimizer
except ImportError as exc:
    print("Missing Qiskit packages. Run:\npython -m pip install qiskit qiskit-algorithms qiskit-optimization")
    print("Import error:", exc)
    sys.exit(1)

@dataclass
class Process:
    pid: str
    arrival: int
    burst: int
    priority: int

@dataclass
class Segment:
    pid: str
    start: int
    end: int

ALGORITHMS = ["FCFS", "SJF", "Priority", "Round Robin"]

def read_int(prompt, minimum=0):
    while True:
        try:
            v = int(input(prompt))
            if v < minimum:
                print(f"Enter a value >= {minimum}.")
                continue
            return v
        except ValueError:
            print("Enter a valid integer.")

def get_input():
    print("=" * 52 + "\n       QUANTUM MULTI-CORE SCHEDULER\n" + "=" * 52)
    n = read_int("\nProcesses: ", 1)
    cores = read_int("CPU Cores: ", 1)
    quantum = read_int("Round Robin time quantum (e.g. 2): ", 1)
    ps = []
    for i in range(n):
        print(f"\nP{i+1}")
        ps.append(Process(f"P{i+1}", read_int("  Arrival Time (AT): ", 0),
                          read_int("  Burst Time (BT): ", 1),
                          read_int("  Priority (smaller = higher): ", 1)))
    if n * cores > 22:
        print(f"Warning: {n*cores} QUBO variables may make statevector simulation slow.")
        print("For a first test, use 4-6 processes and 2-3 cores.")
    return ps, cores, quantum

def simulate(ps, algorithm, quantum):
    if not ps:
        return [], {}
    pending = sorted(ps, key=lambda p: (p.arrival, int(p.pid[1:])))
    rem = {p.pid: p.burst for p in ps}
    first, complete, segs = {}, {}, []
    now, done, idx, queue = 0, set(), 0, []
    byid = {p.pid: p for p in ps}
    if algorithm != "Round Robin":
        while len(done) < len(ps):
            ready = [p for p in pending if p.pid not in done and p.arrival <= now]
            if not ready:
                now = min(p.arrival for p in pending if p.pid not in done)
                ready = [p for p in pending if p.pid not in done and p.arrival <= now]
            if algorithm == "FCFS":
                p = min(ready, key=lambda x: (x.arrival, int(x.pid[1:])))
            elif algorithm == "SJF":
                p = min(ready, key=lambda x: (x.burst, x.arrival, int(x.pid[1:])))
            else:
                p = min(ready, key=lambda x: (x.priority, x.arrival, int(x.pid[1:])))
            first.setdefault(p.pid, now)
            segs.append(Segment(p.pid, now, now + p.burst))
            now += p.burst
            complete[p.pid] = now
            done.add(p.pid)
    else:
        while len(done) < len(ps):
            while idx < len(pending) and pending[idx].arrival <= now:
                queue.append(pending[idx].pid); idx += 1
            if not queue:
                if idx < len(pending):
                    now = pending[idx].arrival
                    continue
                break
            pid = queue.pop(0)
            first.setdefault(pid, now)
            run = min(quantum, rem[pid])
            segs.append(Segment(pid, now, now + run))
            now += run
            rem[pid] -= run
            while idx < len(pending) and pending[idx].arrival <= now:
                queue.append(pending[idx].pid); idx += 1
            if rem[pid]:
                queue.append(pid)
            else:
                complete[pid] = now
                done.add(pid)
    metrics = {}
    for p in ps:
        tat = complete[p.pid] - p.arrival
        metrics[p.pid] = {"completion": complete[p.pid], "turnaround": tat,
                          "waiting": tat-p.burst, "response": first[p.pid]-p.arrival}
    return segs, metrics

def baseline_report(ps, q):
    print("\n" + "="*52 + "\n       ALGORITHM ANALYSIS\n" + "="*52)
    out = {}
    for alg in ALGORITHMS:
        _, m = simulate(ps, alg, q)
        out[alg] = sum(v["waiting"] for v in m.values()) / len(ps)
        print(f"\n{alg}\nAverage Waiting Time    : {out[alg]:.2f}")
    return out

def build_qubo(ps, k):
    """x_i_c binary; penalty enforces one core/process; quadratic term balances burst load."""
    qp = QuadraticProgram("process_core_assignment")
    var = {}
    for i in range(len(ps)):
        for c in range(k):
            name = f"x_{i}_{c}"
            var[i, c] = name
            qp.binary_var(name=name)
    total = sum(p.burst for p in ps)
    avg = total / k
    A = max(10.0, 2.0 * sum(p.burst**2 for p in ps))
    B = 1.0
    lin = {name: 0.0 for name in var.values()}
    quad = {}
    # A*(1 - sum_c x_i_c)^2, using x^2=x; constant A omitted.
    for i in range(len(ps)):
        for c in range(k):
            lin[var[i,c]] -= A
        for c1 in range(k):
            for c2 in range(c1+1, k):
                key = (var[i,c1], var[i,c2])
                quad[key] = quad.get(key, 0.0) + 2*A
    # B*sum_c(load_c - average_load)^2
    for c in range(k):
        for i, p in enumerate(ps):
            lin[var[i,c]] += B*(p.burst**2 - 2*avg*p.burst)
        for i in range(len(ps)):
            for j in range(i+1, len(ps)):
                key = (var[i,c], var[j,c])
                quad[key] = quad.get(key, 0.0) + 2*B*ps[i].burst*ps[j].burst
    lin = {n:v for n,v in lin.items() if abs(v)>1e-12}
    quad = {key:v for key,v in quad.items() if abs(v)>1e-12}
    # Restore constants omitted when expanding the squared expressions:
    # A * N from the one-core-per-process penalty and B * K * average_load^2
    # from the workload-balancing objective. Without these constants, the
    # optimizer is unchanged, but the reported objective is shifted.
    constant = len(ps) * A + k * B * (avg ** 2)
    qp.minimize(constant=constant, linear=lin, quadratic=quad)
    return qp, var

def qaoa_assign(ps, k):
    qp, var = build_qubo(ps, k)
    print("\n" + "="*52 + "\n       QUANTUM OPTIMIZATION\n" + "="*52)
    print("\nQUBO formulated")
    print(f"Binary variables: {len(var)}")
    print("QAOA: QAOA + COBYLA + local StatevectorSampler")
    sampler = StatevectorSampler(seed=17)
    qaoa = QAOA(sampler=sampler, optimizer=COBYLA(maxiter=20), reps=1)
    result = MinimumEigenOptimizer(qaoa).solve(qp)
    assignment = {}
    for i, p in enumerate(ps):
        vals = [float(result.x[qp.variables_index[var[i,c]]]) for c in range(k)]
        assignment[p.pid] = max(range(k), key=lambda c: vals[c])
    print("QAOA executed using local quantum-circuit simulation")
    print(f"Full QUBO objective value: {result.fval:.3f}")
    print("Lower objective values are preferred for this model.")
    return assignment

def evaluate(ps, k, assignment, algs, quantum):
    groups = [[] for _ in range(k)]
    for p in ps:
        groups[assignment[p.pid]].append(p)
    allm, allsegs, loads, finishes, busy = {}, [], [], [], []
    for c in range(k):
        segs, m = simulate(groups[c], algs[c], quantum)
        allsegs.append(segs); allm.update(m)
        loads.append(sum(p.burst for p in groups[c]))
        finishes.append(max((s.end for s in segs), default=0))
        busy.append(sum(s.end-s.start for s in segs))
    n = len(ps)
    aw = sum(allm[p.pid]["waiting"] for p in ps)/n
    at = sum(allm[p.pid]["turnaround"] for p in ps)/n
    ar = sum(allm[p.pid]["response"] for p in ps)/n
    imbalance = max(loads)-min(loads)
    makespan = max(finishes, default=0)
    util = 100*sum(busy)/(k*makespan) if makespan else 0.0
    switches = sum(sum(a.pid != b.pid for a,b in zip(s,s[1:])) for s in allsegs)
    # Classical policy-selection score for a fixed QAOA assignment.
    score = aw + 0.10*at + 0.02*switches
    return {"score":score, "avg_wait":aw, "avg_turn":at, "avg_response":ar,
            "imbalance":imbalance, "utilization":util, "switches":switches,
            "assignment":assignment.copy(), "algorithms":list(algs), "groups":groups,
            "segments":allsegs, "metrics":allm}

def choose_policies(ps, k, assignment, q):
    if k <= 5:
        candidates = product(ALGORITHMS, repeat=k)
        best = None
        for algs in candidates:
            r = evaluate(ps, k, assignment, list(algs), q)
            if best is None or r["score"] < best["score"]:
                best = r
        return best
    # Coordinate descent for larger core counts.
    algs = [ALGORITHMS[0]]*k
    best = evaluate(ps, k, assignment, algs, q)
    changed = True
    while changed:
        changed = False
        for c in range(k):
            for alg in ALGORITHMS:
                trial = algs.copy(); trial[c] = alg
                r = evaluate(ps, k, assignment, trial, q)
                if r["score"] < best["score"]:
                    algs, best, changed = trial, r, True
    return best

def print_final(ps, r):
    print("\nSelected allocation:\n")
    for c, alg in enumerate(r["algorithms"]):
        print(f"Core {c+1} → {alg}")
    print("\nProcess allocation:\n")
    for c, group in enumerate(r["groups"]):
        print(f"Core {c+1} → {', '.join(p.pid for p in group) or '(idle)'}")
    print("\n" + "="*52 + "\n       FINAL PERFORMANCE\n" + "="*52)
    print(f"\nAverage Waiting Time : {r['avg_wait']:.2f}")
    print(f"Average Turnaround   : {r['avg_turn']:.2f}")
    print(f"Average Response     : {r['avg_response']:.2f}")
    print(f"Load Imbalance       : {r['imbalance']}")
    print(f"CPU Utilization      : {r['utilization']:.1f}%")
    print(f"Context Switches     : {r['switches']}")
    print("\nPer-process metrics:")
    print(f"{'Process':<9}{'Core':<7}{'CT':<7}{'WT':<7}{'TAT':<7}{'RT':<7}")
    for p in ps:
        m = r["metrics"][p.pid]
        print(f"{p.pid:<9}{r['assignment'][p.pid]+1:<7}{m['completion']:<7}"
              f"{m['waiting']:<7}{m['turnaround']:<7}{m['response']:<7}")
    print("\nPer-core Gantt segments:")
    for c, segs in enumerate(r["segments"]):
        body = " | ".join(f"{s.pid}[{s.start}-{s.end}]" for s in segs) or "(idle)"
        print(f"Core {c+1}: {body}")
    print("\nRecommended Strategy: HYBRID QUANTUM SCHEDULING")
    print("QAOA: process-to-core assignment on a local circuit simulator.")
    print("Classical post-processing: scheduling-policy selection per core.")

def main():
    ps, k, q = get_input()
    baseline_report(ps, q)
    assignment = qaoa_assign(ps, k)
    result = choose_policies(ps, k, assignment, q)
    print_final(ps, result)

if __name__ == "__main__":
    main()
