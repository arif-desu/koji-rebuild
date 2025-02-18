#! /usr/bin/env python3

from koji_rebuild.setup import Setup


def main(configfile):
    config = Setup(configfile)
    upstream = config.get_koji_session("upstream")

    print(upstream.hello())


if __name__ == "__main__":
    configfile = "config.yaml"
    main(configfile)
