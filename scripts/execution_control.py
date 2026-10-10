"""Bound subprocess work; persist wall-clock phase evidence, including failures."""
import argparse
import json
import os
import subprocess
import time
from pathlib import Path

PHASES = ('discovery', 'network', 'parse', 'ocr', 'review', 'mapping', 'visual_review', 'machine_audit', 'selection', 'export', 'environment')


class PhaseLedger:
    def __init__(self, path):
        self.path = Path(path)
        self.data = json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else {'started_unix': time.time(), 'events': []}
        if not self.path.exists():
            self.path.parent.mkdir(parents=True,exist_ok=True)
            self.path.write_text(json.dumps(self.data,ensure_ascii=False,indent=2),encoding='utf8')

    def start_phase(self,phase,label):
        if phase not in PHASES or not label:raise ValueError('Valid phase and label required')
        active=self.data.setdefault('active_phases',{})
        if label in active:raise ValueError('Phase label already active')
        active[label]={'phase':phase,'started_unix':time.time()}
        self.path.write_text(json.dumps(self.data,ensure_ascii=False,indent=2),encoding='utf8')

    def finish_phase(self,label,status='ok'):
        active=self.data.setdefault('active_phases',{})
        if label not in active:raise ValueError('Phase label not active')
        entry=active.pop(label);self.record(entry['phase'],entry['started_unix'],status,{'label':label})

    def record(self, phase, started, status, detail=None):
        if phase not in PHASES:
            raise ValueError('Unknown phase')
        self.data['events'].append({'phase': phase, 'started_unix': started, 'ended_unix': time.time(), 'status': status, 'detail': detail})
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding='utf-8')

    def summary(self, new_values=None):
        now = time.time()
        totals = {p: sum(e['ended_unix'] - e['started_unix'] for e in self.data['events'] if e['phase'] == p) for p in PHASES}
        # Union of intervals avoids subtracting parallel task time twice.
        intervals = sorted((e['started_unix'], e['ended_unix']) for e in self.data['events'])
        merged = []
        for a, b in intervals:
            if merged and a <= merged[-1][1]:
                merged[-1][1] = max(b, merged[-1][1])
            else:
                merged.append([a, b])
        wall = now - self.data['started_unix']
        accounted = sum(b - a for a, b in merged)
        return {'wall_seconds': wall, 'phase_seconds': totals, 'unattributed_seconds': max(0, wall - accounted),
                'open_phases':self.data.get('active_phases',{}),
                'unattributed_note': 'Includes agent/tool gaps and user waiting; not measured model inference time.',
                'seconds_per_100_new_values': wall * 100 / new_values if new_values and new_values > 0 else None,
                'tokens': None, 'energy': None}


def run_job(job, ledger):
    argv = job['argv']
    if not isinstance(argv, list) or not argv or not all(isinstance(v, str) for v in argv):
        raise ValueError('argv must be a nonempty string list; shell command strings are forbidden')
    phase = job['phase']
    if phase not in PHASES:
        raise ValueError('Unknown phase')
    timeout = float(job.get('timeout_seconds', 120))
    if not 0 < timeout <= 1800:
        raise ValueError('timeout_seconds must be >0 and <=1800')
    started = time.time()
    try:
        process = subprocess.run(argv, shell=False, cwd=job.get('cwd'), timeout=timeout, capture_output=True, env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
        status = 'ok' if process.returncode == 0 else 'failed'
        result = {'status': status, 'returncode': process.returncode, 'stdout': process.stdout.decode('utf-8', errors='replace'), 'stderr': process.stderr.decode('utf-8', errors='replace')}
    except subprocess.TimeoutExpired:
        result = {'status': 'budget_exhausted', 'returncode': 124, 'retryable_automatically': False, 'data_complete': False}
    except OSError as exc:
        result = {'status': 'failed', 'returncode': 1, 'reason': str(exc)}
    ledger.record(phase, started, result['status'], {'timeout_seconds': timeout, 'returncode': result['returncode']})
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--ledger', required=True)
    p.add_argument('--job', help='JSON with argv list, phase, timeout_seconds, optional cwd')
    p.add_argument('--new-values', type=int)
    p.add_argument('--start-phase',choices=PHASES);p.add_argument('--finish-phase',action='store_true');p.add_argument('--label')
    p.add_argument('--output', required=True)
    a = p.parse_args()
    ledger = PhaseLedger(a.ledger)
    if a.start_phase:ledger.start_phase(a.start_phase,a.label)
    if a.finish_phase:ledger.finish_phase(a.label)
    result = run_job(json.loads(Path(a.job).read_text(encoding='utf-8-sig')), ledger) if a.job else ledger.summary(a.new_values)
    Path(a.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k not in ('stdout', 'stderr')}, ensure_ascii=False))
    return result.get('returncode', 0)


if __name__ == '__main__':
    raise SystemExit(main())
