#!/usr/bin/env python3
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
from common import Error, allowed_url, boolean, compose, docker_build, env_file, fetch_ca_bundle, local_image, need, run, sha, write_json
import sources
import dependency_policy
from render import render
ROOT = Path(__file__).resolve().parent.parent

def build_inputs(env):
    sources.verify(ROOT)
    dependency_policy.check(ROOT, env)
    for key in ('BASE_IMAGE', 'PYTHON_BUILDER_IMAGE', 'NODE_BUILDER_IMAGE'):
        local_image(need(env, key), env)
        ensure_image(env[key])
    for key in ('PIP_INDEX_URL', 'NPM_REGISTRY'):
        allowed_url(need(env, key), env)
    fetch_ca_bundle(ROOT, env)
    args = {k: need(env,k) for k in ('BASE_IMAGE', 'PYTHON_BUILDER_IMAGE', 'NODE_BUILDER_IMAGE', 'PIP_INDEX_URL', 'NPM_REGISTRY')}
    args['PNPM_VERSION'] = env.get('PNPM_VERSION') or '10'
    args['DOCKER_CLI_PACKAGE'] = need(env, 'DOCKER_CLI_PACKAGE')
    args['PIP_VERSION'] = env.get('PIP_VERSION') or '25.2'
    secrets = {}
    for key, name in [('PIP_CONFIG_FILE','pip_config'), ('NPM_CONFIG_FILE','npm_config')]:
        if env.get(key):
            secrets[name] = ROOT / env[key]
            if not secrets[name].is_file():
                raise Error(f'{key}: secret file missing')
    return args, secrets

def ensure_image(image):
    """Pull a base or builder image from its registry when it is not present locally."""
    if subprocess.run(['docker', 'image', 'inspect', image], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
        print(f'Pulling {image}')
        run('docker', 'pull', image, stdout=subprocess.DEVNULL)

def image_map(env):
    result = {'server': need(env,'SERVER_IMAGE'), 'web': need(env,'WEB_IMAGE')}
    if boolean(env, 'ENABLE_AGENT', True):
        result.update(agent=need(env,'AGENT_IMAGE'), task=need(env,'TASK_IMAGE'))
    return result

def main():
    parser = argparse.ArgumentParser(description='ClearML source-based offline installer')
    parser.add_argument('command', choices=['prepare','trust','preflight','dependencies','build','configure','install','status','verify','bundle','load'])
    parser.add_argument('--env', default='.env')
    parser.add_argument('--archive', help='Image archive for load command')
    args = parser.parse_args()
    env = env_file(ROOT / args.env)
    command = args.command
    if command == 'prepare':
        sources.prepare(ROOT, env)
    elif command == 'trust':
        fetch_ca_bundle(ROOT, env)
    elif command in ('dependencies','build'):
        build_args, secret_files = build_inputs(env)
        if command == 'dependencies':
            if (ROOT / 'wheelhouse').exists():
                raise Error('wheelhouse already exists; preserve it or explicitly remove it to resolve new dependencies')
            tag = need(env,'SERVER_IMAGE') + '-dependencies'
            docker_build(ROOT, env, 'containers/Containerfile', tag, build_args, secret_files, 'python-resolve')
            container = run('docker', 'create', tag, 'true', capture_output=True, text=True).stdout.strip()
            try:
                run('docker','cp', f'{container}:/wheelhouse', ROOT / 'wheelhouse')
            finally:
                run('docker','rm', container)
            write_json(ROOT / 'wheelhouse/source-lock.json', json.loads((ROOT / 'sources.lock.json').read_text()))
            print('Dependency wheels and their hash lock are staged in wheelhouse/')
        else:
            sources.verify(ROOT)
            if not (ROOT / 'wheelhouse/source-lock.json').is_file():
                raise Error('Run dependencies once to resolve and lock Python wheels')
            if json.loads((ROOT / 'wheelhouse/source-lock.json').read_text()) != json.loads((ROOT / 'sources.lock.json').read_text()):
                raise Error('Dependency wheels belong to different sources')
            for target, tag in image_map(env).items():
                local_image(tag, env)
                docker_build(ROOT, env, 'containers/Containerfile', tag, build_args, secret_files, target)
            metadata = {}
            for target, image in image_map(env).items():
                metadata[target] = json.loads(run('docker','image','inspect', image, capture_output=True, text=True).stdout)[0]['Id']
            write_json(ROOT / 'generated/build-images.json', metadata)
    elif command == 'configure':
        render(ROOT, env)
        print('Configuration rendered in generated/ (contains secrets)')
    elif command in ('preflight','install'):
        render(ROOT, env)
        run('docker','info', stdout=subprocess.DEVNULL)
        compose(ROOT,'config','--quiet')
        for image in image_map(env).values():
            run('docker','image','inspect',image, stdout=subprocess.DEVNULL)
        compose(ROOT,'run','--rm','--no-deps','apiserver','check-databases')
        if command == 'install':
            for key in ('DATA_DIR','LOG_DIR'):
                path = ROOT / need(env,key)
                path.mkdir(parents=True, exist_ok=True)
            compose(ROOT,'up','-d','--no-build','--pull','never','--wait','--wait-timeout','300')
    elif command == 'status':
        compose(ROOT,'ps')
    elif command == 'verify':
        compose(ROOT,'run','--rm','--no-deps','apiserver','check-databases')
        import urllib.request
        for key, suffix in [('CLEARML_API_URL','/debug.ping'),('CLEARML_WEB_URL','/'),('CLEARML_FILES_URL','/')]:
            with urllib.request.urlopen(need(env,key).rstrip('/') + suffix, timeout=20) as response:
                if response.status != 200:
                    raise Error(f'{key} health check failed')
            print(key + ': healthy')
        print('Run the documented authenticated acceptance test for experiment/artifact/task verification.')
    elif command == 'bundle':
        sources.verify(ROOT)
        destination = ROOT / 'dist'
        destination.mkdir(exist_ok=True)
        archive = destination / 'images.tar'
        run('docker','save','-o',archive,*image_map(env).values())
        # Explicit allowlist avoids collecting real .env, generated secrets or database volumes.
        with tarfile.open(destination / 'installer.tar.gz','w:gz') as bundle:
            for name in ('clearmlctl','scripts','containers','.env.example','.dockerignore','sources.json','sources.lock.json','README.md'):
                bundle.add(ROOT/name, arcname=name, filter=lambda t: None if '__pycache__' in t.name else t)
            for name in json.loads((ROOT/'sources.json').read_text()):
                bundle.add(ROOT/name, arcname=name, filter=lambda t: None if '/.git/' in t.name or t.name.endswith('/.git') else t)
            if (ROOT/'wheelhouse').exists():
                bundle.add(ROOT/'wheelhouse',arcname='wheelhouse')
        write_json(destination / 'checksums.json', {p.name: sha(p) for p in (archive,destination/'installer.tar.gz')})
        print('Bundle exported without site credentials; transfer site configuration separately.')
    elif command == 'load':
        path = Path(args.archive) if args.archive else ROOT/'dist/images.tar'
        checksums = json.loads((path.parent/'checksums.json').read_text())
        if sha(path) != checksums[path.name]:
            raise Error('Image bundle checksum mismatch')
        run('docker','load','-i',path)

if __name__ == '__main__':
    try:
        main()
    except (Error, OSError, ValueError, subprocess.CalledProcessError) as error:
        # Never print subprocess arguments or full connection errors: they can contain secrets.
        print(f'Error: {error if isinstance(error, Error) else type(error).__name__}',file=sys.stderr)
        sys.exit(1)
