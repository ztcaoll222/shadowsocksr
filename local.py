# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, \
    with_statement

import json
import sys
import os
import logging
import signal
from multiprocessing.pool import Pool

from shadowsocks.common import to_bytes, to_str

configs = None


def read_config(filename):
    with open(filename, 'r', encoding='utf-8') as f:
        try:
            j = json.loads(f.read())
            return j
        except:
            pass


if __name__ == '__main__':
    configs = read_config('gui-config.json')

    import inspect
    file_path = os.path.dirname(os.path.realpath(inspect.getfile(inspect.currentframe())))
    sys.path.insert(0, os.path.join(file_path, '../'))

from shadowsocks import shell, daemon, eventloop, tcprelay, udprelay, asyncdns


def run(server, server_port, password, local_address, local_port, method, protocol, protocol_param, obfs, obfs_param):
    shell.check_python()

    # fix py2exe
    if hasattr(sys, "frozen") and sys.frozen in \
            ("windows_exe", "console_exe"):
        p = os.path.dirname(os.path.abspath(sys.executable))
        os.chdir(p)

    config = shell.get_config(True)

    if not config.get('dns_ipv6', False):
        asyncdns.IPV6_CONNECTION_SUPPORT = False

    config['server_port'] = int(server_port)
    config['password'] = to_bytes(password)
    config['local_port'] = int(local_port)
    config['server'] = to_str(server)
    config['method'] = to_str(method)
    config['protocol'] = to_str(protocol)
    config['obfs'] = to_str(obfs)
    config['protocol_param'] = to_str(protocol_param)
    config['obfs_param'] = to_str(obfs_param)
    config['local_address'] = to_str(local_address)

    daemon.daemon_exec(config)
    logging.info("local start with protocol[%s] password [%s] method [%s] obfs [%s] obfs_param [%s]" %
                 (config['protocol'], config['password'], config['method'], config['obfs'], config['obfs_param']))

    try:
        logging.info("starting local at %s:%d" %
                     (config['local_address'], config['local_port']))

        dns_resolver = asyncdns.DNSResolver()
        tcp_server = tcprelay.TCPRelay(config, dns_resolver, True)
        udp_server = udprelay.UDPRelay(config, dns_resolver, True)
        loop = eventloop.EventLoop()
        dns_resolver.add_to_loop(loop)
        tcp_server.add_to_loop(loop)
        udp_server.add_to_loop(loop)

        def handler(signum, _):
            logging.warn('received SIGQUIT, doing graceful shutting down..')
            tcp_server.close(next_tick=True)
            udp_server.close(next_tick=True)

        signal.signal(getattr(signal, 'SIGQUIT', signal.SIGTERM), handler)

        def int_handler(signum, _):
            sys.exit(1)

        signal.signal(signal.SIGINT, int_handler)

        daemon.set_user(config.get('user', None))
        loop.run()
    except Exception as e:
        shell.print_exception(e)
        sys.exit(1)


def check_config(configs, max_port):
    if configs is None:
        logging.error('configs is None')
        exit()
    start = int(configs['localPort'])

    service_conf = configs['configs']
    maxp = max(len(service_conf), max_port)

    for i in range(maxp):
        config = service_conf[i]
        if -1 == config.get('local_address', -1):
            config['local_address'] = "0.0.0.0"

        if -1 == config.get('local_port', -1):
            config['local_port'] = start
        start += 1

    return configs


def main(configs, max_port=5):
    conf = check_config(configs, max_port)

    service_conf = conf['configs']

    # run(server=config['server'],
    #     server_port=config['server_port'],
    #     password=config['password'],
    #     local_address=config['local_address'],
    #     local_port=config['local_port'],
    #     method=config['method'],
    #     protocol=config['protocol'],
    #     protocol_param=config['protocolparam'],
    #     obfs=config['obfs'],
    #     obfs_param=config['obfsparam'])

    if len(service_conf) > max_port:
        max_port = max_port
    else:
        max_port = len(service_conf)

    p = Pool(max_port)
    for i in range(max_port):
        config = service_conf[i]
        p.apply_async(run, args=(config['server'],
                                 config['server_port'],
                                 config['password'],
                                 config['local_address'],
                                 config['local_port'],
                                 config['method'],
                                 config['protocol'],
                                 config['protocolparam'],
                                 config['obfs'],
                                 config['obfsparam'],))

    p.close()
    p.join()


if __name__ == "__main__":
    main(configs)
