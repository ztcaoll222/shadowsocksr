# -*- coding: utf-8 -*-
from collections import OrderedDict


class Haproxy:
    def __init__(self):
        self.section = OrderedDict()

    def add_section(self, section):
        if type(section) is not str:
            return

        if -1 == self.section.get(section, -1):
            self.section[section] = OrderedDict()

    def set(self, section, option, value=None):
        if type(section) is not str:
            return

        node = self.section.get(section, -1)
        if -1 == node:
            self.add_section(section)

        node = self.section.get(section)
        node[option] = value

    def write(self, fp):
        for key, value in self.section.items():
            fp.write(key)
            fp.write('\n')
            for k, v in value.items():
                fp.write(' '*4+k)
                fp.write(' ')
                fp.write(v)
                fp.write('\n')


if __name__ == "__main__":
    conf = Haproxy()
    conf.add_section('global')
    conf.set("global", "nbproc", str(2))
    conf.set("global", "chroot", '/root/proxy/')
    conf.set("global", "pidfile", '/root/proxy/haproxy.pid')
    conf.set("global", "stats socket", '/root/proxy/haproxy_stats')
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
    conf.set("defaults", "timeout connect", '5000ms')
    conf.set("defaults", "timeout client", '30000ms')
    conf.set("defaults", "timeout server", '30000ms')
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
    conf.set("listen admin_stats", "auth", 'admin:admin')
    conf.set("listen admin_stats", "hide-version", '')
    conf.set("listen admin_stats", "admin", 'if TRUE')

    conf.add_section('frontend ss-in')
    conf.set("frontend ss-in", "bind", '127.0.0.1:8388')
    conf.set("frontend ss-in", "default_backend", 'ss-out')

    conf.add_section('backend ss-out')
    conf.set("backend ss-out", "mode", 'tcp')
    conf.set("backend ss-out", "balance", 'roundrobin')
    conf.set("backend ss-out", "option", 'tcplog')
    conf.set("backend ss-out", "server 0", '127.0.0.1:8388')

    with open('haproxy.cfg', 'w', encoding='utf-8') as f:
        conf.write(f)
