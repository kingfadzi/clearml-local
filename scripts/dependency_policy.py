"""Reject known package-manager bypasses before contacting internal registries."""
import configparser
import json
import re
from common import Error, allowed_url

def check(root, env):
    for name in ('clearml-server/apiserver/requirements.txt','clearml/pyproject.toml','clearml-agent/pyproject.toml',
                 'clearml/setup.py','clearml-agent/setup.py'):
        path=root/name
        if not path.exists(): continue
        content=path.read_text()
        if name.endswith('requirements.txt'):
            for line in content.splitlines():
                if line.strip().startswith(('-i ','--index-url','--extra-index-url','-f ','--find-links','-r ','--requirement')):
                    raise Error(f'{name}: nested or alternate dependency source requires review')
                if 'git+' in line or 'git://' in line:
                    raise Error(f'{name}: Git dependency is forbidden')
                for url in re.findall(r'https?://[^\s\]\)\"\']+',line): allowed_url(url,env)
    package=json.loads((root/'clearml-web/package.json').read_text())
    for group in ('dependencies','devDependencies','optionalDependencies'):
        for value in package.get(group,{}).values():
            if value.startswith(('git:','git+','github:','gitlab:','bitbucket:')):
                raise Error('Frontend Git dependency is forbidden')
            if value.startswith(('http://','https://')): allowed_url(value,env)
    npmrc=root/'clearml-web/.npmrc'
    if npmrc.exists():
        for line in npmrc.read_text().splitlines():
            key,sep,value=line.partition('=')
            if sep and key.strip().endswith('registry'): allowed_url(value.strip(),env)
            if sep and key.strip() in ('_auth','_authToken') or ':_authToken' in key: raise Error('Frontend .npmrc must not embed credentials')
    for line in (root/'clearml-web/pnpm-lock.yaml').read_text().splitlines():
        if 'tarball:' in line:
            for url in re.findall(r'https?://[^\s,}\"\']+',line): allowed_url(url,env)
        # Package names such as @npmcli/git@7.0.1 are not Git URLs.
        if re.search(r"git\+|git@[\w.-]+:|\bgit://", line):
            raise Error('Frontend lock contains a Git dependency')
    if env.get('PIP_CONFIG_FILE'):
        parser=configparser.ConfigParser(interpolation=None);parser.read(root/env['PIP_CONFIG_FILE'])
        for section in parser.sections():
            for key,value in parser[section].items():
                if key in ('extra-index-url','find-links') and value.strip():
                    raise Error('pip secret must not add indexes or find-links')
                if key=='index-url': allowed_url(value,env)
    if env.get('NPM_CONFIG_FILE'):
        for line in (root/env['NPM_CONFIG_FILE']).read_text().splitlines():
            key,sep,value=line.partition('=')
            if sep and key.strip().endswith('registry'): allowed_url(value.strip(),env)
