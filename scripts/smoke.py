#!/usr/bin/env python3
"""Authenticated SDK acceptance test. Creates one clearly named test experiment."""
import tempfile
from pathlib import Path
from clearml import Task

def main():
    task = Task.init(project_name='Offline installer verification',task_name='Artifact round trip',
                     auto_connect_frameworks=False, auto_connect_arg_parser=False)
    try:
        task.get_logger().report_scalar('offline-install','smoke',1,iteration=0)
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'offline-proof.txt';path.write_text('ClearML offline artifact verification\n')
            task.upload_artifact(name='offline-proof',artifact_object=path,wait_on_upload=True)
            task.flush(wait_for_uploads=True)
            task.reload()
            downloaded=Path(task.artifacts['offline-proof'].get_local_copy())
            if downloaded.read_bytes() != path.read_bytes():raise RuntimeError('Artifact round trip mismatch')
        print('Experiment, metric and artifact verified. Task ID:',task.id)
    finally:
        task.close()

if __name__=='__main__':main()
