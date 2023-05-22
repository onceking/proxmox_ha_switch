#! /usr/bin/env python3

from pathlib import Path
import re
import argparse
import subprocess
from urllib import request
import json
import time
import logging


class HA:
    def __init__(self, url, token):
        self.url = url.rstrip('/')
        self._token = token
        assert self.call_ha('')['message'] == 'API running.'

    def call_ha(self, path, data=None, method=None):
        url = f'{self.url}/api/{path}'
        if data:
            data = json.dumps(data).encode('utf-8')
        logging.debug('calling-ha: %s %s', url, data)
        req = request.Request(
            url,
            data=data,
            headers={
                'authorization': f'Bearer {self._token}',
                'content-type': 'application/json'
            },
            method=method)
        return json.loads(request.urlopen(req).read())

def run_qm(*args):
    logging.info("qm %s", " ".join(args))
    subprocess.run(["qm"] + list(args), check=True)

def main():
    logging.basicConfig(
        format='%(asctime)s %(levelname)-8s %(message)s',
        level=logging.DEBUG,
        datefmt='%Y-%m-%d %H:%M:%S')

    parser = argparse.ArgumentParser(description='Proxmox Home Assistant Switch')
    parser.add_argument('--ha-url', type=str, required=True)
    parser.add_argument('--ha-prefix', type=str, required=True)
    parser.add_argument('--ha-token-path', type=str, required=True)
    parser.add_argument('--healthcheck', type=str, required=True)
    args = parser.parse_args()
    print(args)
    id_prefix = f"input_boolean.proxmox_{args.ha_prefix}_"

    ha = HA(args.ha_url, Path(args.ha_token_path).read_text().strip())
    # devs: Mapping[str, Device] = {}

    while True:
        now = int(time.time())
        wants = {}
        currents = {}
        for state in ha.call_ha("states"):
            # input_boolean.proxmox_vmhost_tax
            if state['entity_id'].startswith(id_prefix):
                name = state['entity_id'][len(id_prefix):]
                wants[name] = state['state']

        qm_list = subprocess.run(["qm", "list", "--full"], check=True, stdout=subprocess.PIPE)
        for line in qm_list.stdout.decode('utf-8').splitlines():
            # 100 tax                  running    6144              60.00 1954081
            if m := re.match(r'^\s*(\d+)\s+(\S+)\s+(\S+)', line):
                currents[m.group(2)] = {
                    "id": m.group(1), 
                    "state": m.group(3)
                }
        logging.debug("wants=%s currents=%s", json.dumps(wants), json.dumps(currents))

        for name in (set(currents) & set(wants)):
            current = currents[name]
            if wants[name] == 'on':
                if current["state"] == "paused":
                    run_qm("resume", current["id"])
                elif current["state"] == "stopped":
                    run_qm("start", current["id"])

            elif wants[name] == 'off':
                if current["state"] == "running":
                    run_qm("suspend", current["id"])
                    
        if args.healthcheck:
            request.urlopen(f'https://hc-ping.com/{args.healthcheck}').read()

        while time.time() - now < 30:
            time.sleep(1)
main()
