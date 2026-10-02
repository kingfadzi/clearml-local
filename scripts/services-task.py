#!/usr/bin/env python3
"""Acceptance: enqueue a standalone task on the services queue and wait for its outcome."""
import argparse
import sys
import time
from clearml import Task
from clearml.backend_api.session.client import APIClient

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--image', required=True)
    parser.add_argument('--expect', choices=['completed', 'failed'], default='completed')
    parser.add_argument('--queue', default='services')
    parser.add_argument('--timeout', type=int, default=600)
    args = parser.parse_args()
    script = "import clearml, platform\nprint('offline services task ok', clearml.__version__, platform.node())\n"
    task = Task.create(project_name='Offline installer verification', task_name=f'Services task ({args.expect})',
                       script='offline_task.py', docker=args.image, add_task_init_call=False)
    task.update_task({'script': {'diff': script, 'entry_point': 'offline_task.py', 'working_dir': '.', 'repository': '',
                                 'requirements': {'pip': ''}}})
    Task.enqueue(task, queue_name=args.queue)
    deadline = time.time() + args.timeout
    while time.time() < deadline:
        task.reload()
        status = str(task.status)
        if status in ('completed', 'failed', 'stopped'):
            break
        time.sleep(5)
    else:
        status = 'timeout'
    log = ''.join(e.get('msg', '') for e in APIClient().events.get_task_log(task=task.id, batch_size=50).events)
    print(f'task {task.id} status={status}')
    print(log[-1500:])
    if status != args.expect:
        sys.exit(f'expected {args.expect}, got {status}')

if __name__ == '__main__':
    main()
