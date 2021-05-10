import sys
import os
import configargparse
from pathlib import Path
from os.path import *
import site
import time
from main.listeners import *
from main.resolver import Resolver
import pykka


def get_resource_dir():
    possibilities = [
        abspath(join(dirname(__file__), '..', 'resources')),
        abspath(join(sys.prefix, 'dns_cached_resolver_resources')),
        abspath(join(site.USER_BASE, 'dns_cached_resolver_resources'))
    ]

    for p in possibilities:
        if Path(p).exists():
            return p


def set_logging_level(level):
    root = logging.getLogger()
    root.setLevel(logging.getLevelName(level))

    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(logging.getLevelName(level))
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    root.addHandler(handler)


def parse_args(argv):
    p = configargparse.ArgParser(default_config_files=[os.path.join(get_resource_dir(), 'config.ini')])
    p.add_argument('-c', '--config', required=False, is_config_file=True, help='Config file path')
    p.add_argument('--logging_level', required=True, help='Logging level')
    p.add_argument('--protocol', required=True, choices=['tcp', 'udp', 'both'], help='')
    p.add_argument('--host', required=True, help='')
    p.add_argument('--port', required=True, type=int, help='')
    p.add_argument('--root_servers', required=True, action='append', help='')
    p.add_argument('--cache_location', required=True, type=expanduser)
    args = p.parse_args(argv)

    return args

def main():
    args = parse_args(sys.argv[1:])
    set_logging_level(args.logging_level)

    resolver_ref = Resolver.start(args.root_servers, args.cache_location)

    if args.protocol in {'tcp', 'both'}:
        ref = TCPListener.start(args.host, args.port, resolver_ref)
        ref.tell({'command': 'start'})

    if args.protocol in {'udp', 'both'}:
        ref = UDPListener.start(args.host, args.port, resolver_ref)
        ref.tell({'command': 'start'})

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info('Interrupted, exiting gracefully')
        pykka.ActorRegistry.stop_all(block=True)
    except Exception as e:
        logging.error('Unhandled exception generated: {}, exiting non-gracefully'.format(e))
        sys.exit(1)


if __name__ == '__main__':
    main()
