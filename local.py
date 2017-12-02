# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, \
    with_statement

import ipaddress
import json
import random
import sys
import os
import logging
import signal
from multiprocessing.pool import Pool

from shadowsocks.common import to_bytes, to_str
from shadowsocks import shell, daemon, eventloop, tcprelay, udprelay, asyncdns
from utils.haproxy import Haproxy


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


def read_config(filename):
    with open(filename, 'r', encoding='utf-8') as f:
        try:
            j = json.loads(f.read())
            return j
        except:
            pass


def rand_pass():
    return ''.join(
        [random.choice('''ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789~-_=+(){}[]^&%$@''') for i in
         range(8)])


def check_config(configs, max_port):
    if configs is None:
        logging.error('configs is None')
        exit()
    if -1 == configs.get('localPort', -1):
        configs['localPort'] = 1080
    start = int(configs['localPort'])

    if -1 == configs.get('localAuthPassword', -1):
        configs['localAuthPassword'] = rand_pass()

    service_conf = configs['configs']
    maxp = max(len(service_conf), max_port)

    i = 0
    while True:
        if i >= len(service_conf):
            break

        config = service_conf[i]
        try:
            ip_type = ipaddress.ip_address(config['server'])
            if isinstance(ip_type, ipaddress.IPv6Address):
                if -1 == config.get('local_address', -1):
                    config['local_address'] = "::1"
            elif isinstance(ip_type, ipaddress.IPv4Address):
                if -1 == config.get('local_address', -1):
                    config['local_address'] = "127.0.0.1"

            if -1 == config.get('local_port', -1):
                config['local_port'] = start
            start += 1
        except ValueError as e:
            service_conf.pop(i)
            continue

        i += 1

    return configs


def write_config(configs, filename):
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(json.dumps(configs, ensure_ascii=False, indent=4))


def write_cfg(server_list, passwd, filename):
    conf = Haproxy()

    conf.add_section('global')
    conf.set("global", "nbproc", str(2))
    conf.set("global", "chroot", '/root/proxy/')
    conf.set("global", "pidfile", '/root/proxy/haproxy.pid')
    conf.set("global", "stats", 'socket /root/proxy/haproxy_stats')
    conf.set("global", "user", 'root')
    conf.set("global", "group", 'root')
    conf.set("global", "ulimit-n", str(51200))
    conf.set("global", "maxconn", str(8192))

    conf.add_section('defaults')
    conf.set("defaults", "log", 'global')
    conf.set("defaults", "mode", 'tcp')
    conf.set("defaults", "retries", str(3))
    conf.set("defaults", "option", 'abortonclose')
    conf.set("defaults", "maxconn", str(8192))
    conf.set("defaults", "timeout", 'connect 5000ms')
    conf.set("defaults", "timeout", 'client 30000ms')
    conf.set("defaults", "timeout", 'server 30000ms')
    conf.set("defaults", "balance", 'roundrobin')
    conf.set("defaults", "log", 'global')

    conf.add_section('listen admin_stats')
    conf.set("listen admin_stats", "bind", '0.0.0.0:1111')
    conf.set("listen admin_stats", "mode", 'http')
    conf.set("listen admin_stats", "option", 'httplog')
    conf.set("listen admin_stats", "maxconn", str(10))
    conf.set("listen admin_stats", "stats refresh", '30s')
    conf.set("listen admin_stats", "uri", '/haproxy')
    conf.set("listen admin_stats", "realm", 'Haproxy')
    conf.set("listen admin_stats", "auth", 'admin:%s' % passwd)
    conf.set("listen admin_stats", "hide-version", '')
    conf.set("listen admin_stats", "admin", 'if TRUE')

    conf.add_section('frontend ss-in')
    conf.set("frontend ss-in", "bind", '127.0.0.1:8388')
    conf.set("frontend ss-in", "default_backend", 'ss-out')

    conf.add_section('backend ss-out')
    conf.set("backend ss-out", "mode", 'tcp')
    conf.set("backend ss-out", "balance", 'roundrobin')
    conf.set("backend ss-out", "option", 'tcplog')
    for i in range(len(server_list)):
        server = server_list[i]
        for addr, port in server.items():
            conf.set("backend ss-out", "server %s" % i, '%s:%s' % (addr, port))
            break

    with open(filename, 'w', encoding='utf-8') as f:
        conf.write(f)


def main(configs, max_port=5):
    conf = check_config(configs, max_port)

    write_config(conf, 'gui-config.json')

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

    server_list = []

    p = Pool(max_port)
    for i in range(max_port):
        config = service_conf[i]

        server_list.append({config['local_address']:config['local_port']})

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

    write_cfg(server_list, conf['localAuthPassword'], 'haproxy.cfg')

    p.close()
    p.join()


if __name__ == "__main__":
    configs = read_config('gui-config.json')
    main(configs)
