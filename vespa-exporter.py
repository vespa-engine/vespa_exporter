#!/usr/bin/env python

import json
import time
import os
from prometheus_client import start_http_server, Gauge
import requests
import logging
import re
from threading import Lock, Thread

http_port = 9426

config_server = os.getenv('VESPA_CONFIGSERVER', 'localhost:19071')
configurl = 'http://' + config_server + '/config/v2/tenant/default/application/default/cloud.config.model/client'
prom_metrics = {}
endpoints = {}

first_cap_re = re.compile('(.)([A-Z][a-z]+)')
all_cap_re = re.compile('([a-z0-9])([A-Z])')

lock = Lock()


def camelcase_convert(name):
    s1 = first_cap_re.sub(r'\1_\2', name)
    return all_cap_re.sub(r'\1_\2', s1).lower()


def get_metrics():
    global endpoints
    try:
        response = requests.get(configurl, timeout=2)
        
        try:
            model = json.loads(response.text)
        except ValueError:
            logger.error('JSON parse failed.')
            raise ValueError

        endpoints = {}
        for host in model['hosts']:
            for service in host['services']:
                for port in service['ports']:
                    if 'http' in port['tags'].split(' ') and 'state' in port['tags'].split(' '):
                        if service['type'] in endpoints:
                            endpoints[service['type']].append(host['name']+':'+str(port['number']))
                        else:
                            endpoints[service['type']] = [host['name']+':'+str(port['number'])]
    except requests.exceptions.RequestException as e:
        logger.error('Request failed (could not update infos from cluster controller %s): %s', config_server, e)
        if not endpoints:
            raise ValueError

    for service_type in ['searchnode', 'distributor']:
        for service_hostport in endpoints[service_type]:
            t = Thread(target=get_standardservice_metrics, args=(service_type, service_hostport))
            t.daemon = True
            t.start()
    for c in endpoints['container']:
        # The comma after "c" is necessary to specify it's a tuple
        t = Thread(target=get_container_metrics, args=(c,))
        t.daemon = True
        t.start()


def get_standardservice_metrics(service_type, hostport):
    service = 'vespa_' + service_type
    (host, port) = hostport.split(':')
    url = 'http://' + host + ':' + port + '/state/v1/metrics'
    try:
        response = requests.get(url, timeout=2)

        try:
            m = json.loads(response.text)
        except ValueError:
            logger.error('JSON parse failed.')
            raise ValueError

        status_code = m['status']['code']
        name = service + '_' + 'status_code_up'
        if name not in prom_metrics:
            prom_metrics[name] = Gauge(name, 'Status code up?', ['host'])
        if status_code == 'up':
            value = 1
        else:
            value = 0
        prom_metrics[name].labels(host=hostport).set(value)

        snapshot_to = m['metrics']['snapshot']['to']
        name = service + '_' + 'snapshot_to'
        if name not in prom_metrics:
            prom_metrics[name] = Gauge(name, 'Snapshot to timestamp', ['host'])
        prom_metrics[name].labels(host=hostport).set(snapshot_to)

        snapshot_from = m['metrics']['snapshot']['from']
        name = service + '_' + 'snapshot_from'
        if name not in prom_metrics:
            prom_metrics[name] = Gauge(name, 'Snapshot from timestamp', ['host'])
        prom_metrics[name].labels(host=hostport).set(snapshot_from)

        for v in m['metrics']['values']:
            name = service + '_' + v['name']
            name = name.replace('.', '_').replace('-', '_')
            name = name.replace('[', '').replace(']', '')
            desc = v['description']
            labels = ['aggregation', 'host']
            labelvalues = {}
            labelvalues['host'] = hostport
            for d in ['documenttype', 'field', 'disk', 'operantiontype']:
                if d in v['dimensions']:
                    labels.append(d)
                    labelvalues[d] = v['dimensions'][d]
            lock.acquire()
            if name not in prom_metrics:
                prom_metrics[name] = Gauge(name, desc, labels)
            lock.release()
            for agg in v['values']:
                labelvalues['aggregation'] = agg
                prom_metrics[name].labels(**labelvalues).set(v['values'][agg])
    except requests.exceptions.RequestException as e:
        prom_metrics[service + '_status_code_up'].labels(host=hostport).set(0)
        logger.error('Request failed (could not update metrics from endpoint %s): %s', hostport, e)

def get_container_metrics(hostport):
    service = 'vespa_container'
    (host, port) = hostport.split(':')
    url = 'http://' + host + ':' + port + '/state/v1/metrics'

    try:
        response = requests.get(url, timeout=2)

        try:
            m = json.loads(response.text)
        except ValueError:
            logger.error('JSON parse failed.')
            raise ValueError

        for v in m['metrics']['values']:
            name = service + '_' + camelcase_convert(v['name'])
            name = name.replace('.', '_').replace('-', '_')
            name = name.replace('[', '').replace(']', '')
            desc = name
            labels = ['aggregation', 'host']
            labelvalues = {}
            labelvalues['host'] = hostport
            if 'dimensions' in v:
                for d in ['chain', 'handler', 'api', 'operation', 'status', 'serverName', 'serverPort']:
                    if d in v['dimensions']:
                        labels.append(d.lower())
                        labelvalues[d.lower()] = v['dimensions'][d]
            lock.acquire()
            if name not in prom_metrics:
                prom_metrics[name] = Gauge(name, desc, labels)
            lock.release()
            for agg in v['values']:
                labelvalues['aggregation'] = agg
                prom_metrics[name].labels(**labelvalues).set(v['values'][agg])

    except requests.exceptions.RequestException as e:
        logger.error('Request failed (could not update metrics from endpoint %s): %s', hostport, e)


def main():
    try:
        start_http_server(http_port)
        while True:
            get_metrics()
            time.sleep(30)
    except KeyboardInterrupt:
        exit(0)


if __name__ == '__main__':
    LOG_LEVEL = logging.getLevelName(os.getenv('LOG_LEVEL', 'DEBUG'))
    logging.basicConfig(format='%(asctime)s %(levelname)s %(message)s',
                        level=LOG_LEVEL)
    logger = logging.getLogger('vespa-exporter')
    main()

