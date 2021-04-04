import sys
import os
import configargparse
import logging
from pathlib import Path
from os.path import *
import site


def get_resource_dir():
    possibilities = [
        abspath(join(dirname(__file__), '..', 'dns_cached_resolver_resources')),
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
    return p.parse_args(argv)


def main():
    args = parse_args(sys.argv[1:])
    set_logging_level(args.logging_level)


if __name__ == '__main__':
    main()
