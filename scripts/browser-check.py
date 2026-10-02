#!/usr/bin/env python3
"""Acceptance: load the UI headlessly, log in, browse, and list every host the browser contacted."""
import json
import sys
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

web = sys.argv[1]
allowed = set(sys.argv[2].split(','))
hosts = {}
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.on('request', lambda r: hosts.setdefault(urlparse(r.url).hostname, set()).add(r.url.split('?')[0][:120]))
    page.on('requestfailed', lambda r: print('FAILED', r.url[:140], r.failure))
    page.on('response', lambda r: print('HTTP', r.status, r.url[:140]) if r.status >= 400 or '/api/' in r.url else None)
    page.on('console', lambda m: print('CONSOLE', m.type, m.text[:160]) if m.type in ('error', 'warning') else None)
    page.goto(web, wait_until='networkidle', timeout=60000)
    print('title:', page.title(), 'url:', page.url)
    page.wait_for_selector('form input', timeout=60000)
    name = page.locator('form input').first
    if name.count():
        name.fill('offline-check')
        page.wait_for_timeout(1000)
        page.locator('form button').first.click()
        try:
            page.wait_for_url(lambda u: '/login' not in u, timeout=30000)
        except Exception as error:
            print('login did not navigate:', type(error).__name__)
            page.screenshot(path='/out/login.png', full_page=True)
            print('page text:', page.inner_text('body')[:600].replace('\n', ' | '))
        page.wait_for_load_state('networkidle', timeout=60000)
        print('after login url:', page.url)
    for path in ('/projects', '/workers-and-queues/workers', '/settings/webapp-configuration'):
        page.goto(web.rstrip('/') + path, wait_until='networkidle', timeout=60000)
        page.wait_for_timeout(3000)
        print('visited', path, '->', page.url)
    browser.close()
external = {h: sorted(u) for h, u in hosts.items() if h not in allowed}
print('hosts contacted:', sorted(h for h in hosts if h))
print('external hosts:', json.dumps(external, indent=1) if external else 'none')
sys.exit(1 if external else 0)
