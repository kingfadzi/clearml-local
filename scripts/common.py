"""Shared, standard-library-only installer utilities. Never executes .env as shell."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import urlparse

class Error(Exception):
    pass

def env_file(path):
    values = {}
    if not path.is_file():
        raise Error(f"Missing {path}; copy .env.example to .env and configure it")
    for n, raw in enumerate(path.read_text().splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        key, sep, value = line.partition('=')
        if not sep or not re.fullmatch(r'[A-Z][A-Z0-9_]*', key):
            raise Error(f"Invalid .env key at line {n}")
        if key in values:
            raise Error(f"Duplicate .env key: {key}")
        if value.startswith(('"', "'")):
            if len(value) < 2 or value[-1] != value[0]:
                raise Error(f"Unclosed quote at line {n}")
            value = value[1:-1]
        values[key] = value
    return values

def need(env, key):
    value = env.get(key, '')
    if not value or 'CHANGE_ME' in value:
        raise Error(f"Configure {key} in .env")
    return value

def boolean(env, key, default=False):
    value = env.get(key, str(default)).lower()
    if value not in ('true', 'false'):
        raise Error(f"{key} must be true or false")
    return value == 'true'

def run(*args, **kwargs):
    return subprocess.run([str(a) for a in args], check=True, **kwargs)

def private_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, 'w') as stream:
        stream.write(content)
    temporary.replace(path)

def write_json(path, value):
    if path.name == 'compose.json':
        def escape(item):
            if isinstance(item, str): return item.replace('$', '$$')
            if isinstance(item, list): return [escape(v) for v in item]
            if isinstance(item, dict): return {k: escape(v) for k,v in item.items()}
            return item
        value = escape(value)
    private_write(path, json.dumps(value, indent=2) + '\n')

def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()

def allowed_url(url, env):
    parsed = urlparse(url)
    hosts = {x.strip() for x in need(env, 'ALLOWED_HOSTS').split(',')}
    if parsed.scheme not in ('http', 'https') or parsed.hostname not in hosts:
        raise Error(f'Repository host is not in ALLOWED_HOSTS: {parsed.hostname}')
    if parsed.username or parsed.password:
        raise Error('Use secret configuration files for repository credentials')
    return url

def local_image(image, env):
    if '/' not in image or urlparse('https://' + image.split('/')[0]).hostname not in {x.strip() for x in need(env, 'ALLOWED_HOSTS').split(',')}:
        raise Error(f"Image registry is not in ALLOWED_HOSTS: {image}")
    if ':latest' in image or (':' not in image.rsplit('/', 1)[-1] and '@sha256:' not in image):
        raise Error('Use a versioned image tag or digest')

def check_repos(root, env):
    """Empty YUM_REPO_FILE keeps the base image's own repositories."""
    import configparser
    if not env.get('YUM_REPO_FILE'):
        return None
    repo = root / env['YUM_REPO_FILE']
    parser = configparser.ConfigParser(interpolation=None)
    try:
        found = parser.read(repo)
    except configparser.Error as error:
        raise Error(f'YUM_REPO_FILE is not a valid repo file: {error}')
    if not found or not parser.sections():
        raise Error('YUM_REPO_FILE must contain repository definitions')
    for section in parser.values():
        if section is parser.defaults():
            continue
        if section.get('mirrorlist') or section.get('metalink'):
            raise Error('YUM repositories must use explicit baseurl values')
        for url in section.get('baseurl', '').split():
            allowed_url(url, env)
        for url in section.get('gpgkey', '').split():
            if not url.startswith('file:///'):
                allowed_url(url, env)
    return repo

def docker_build(root, env, file, tag, args=None, secrets=None, target=None):
    local_image(need(env, 'RUNTIME_BASE_IMAGE'), env)
    command = ['docker', 'build', '--pull=false', '--network', env.get('BUILD_NETWORK', 'default'),
               '-f', str(root / file), '-t', tag]
    for key, value in (args or {}).items():
        command += ['--build-arg', f'{key}={value}']
    for key, path in (secrets or {}).items():
        if path:
            command += ['--secret', f'id={key},src={path}']
    if target:
        command += ['--target', target]
    run(*command, root)

def compose(root, *args):
    run('docker', 'compose', '--project-directory', root, '-f', root / 'generated/compose.json', *args)
