"""Run inside server image before installing; exercise real authenticated clients."""
import json
from pathlib import Path
import sys
from pymongo import MongoClient
from elasticsearch import Elasticsearch
from redis import Redis

base = Path('/opt/clearml/config')
hosts = json.loads((base / 'hosts.conf').read_text())
secure = json.loads((base / 'secure.conf').read_text())
failed = False
for name, config in hosts['mongo'].items():
    try:
        with MongoClient(config['host'], serverSelectionTimeoutMS=10000) as client:
            client.admin.command('ping')
            print('MongoDB', name, client.server_info()['version'])
    except Exception as error:
        print('MongoDB', name, type(error).__name__, file=sys.stderr)
        failed = True
for name, config in hosts['elastic'].items():
    try:
        with Elasticsearch(config['hosts'], basic_auth=(secure['elastic']['user'],secure['elastic']['password']), **config['args']) as client:
            print('Elasticsearch', name, client.info()['version']['number'])
    except Exception as error:
        print('Elasticsearch', name, type(error).__name__, file=sys.stderr)
        failed = True
for name, config in hosts['redis'].items():
    try:
        client = Redis(**config, password=secure['redis'][name]['password'], socket_connect_timeout=10, socket_timeout=10)
        client.ping()
        print('Redis', name, client.info()['redis_version'])
    except Exception as error:
        print('Redis', name, type(error).__name__, file=sys.stderr)
        failed = True
sys.exit(1 if failed else 0)
