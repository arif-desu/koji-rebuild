from koji_rebuild.setup import Setup
from koji_rebuild.package import PackageHelper

import sys


def main(configfile, pkg):
    config = Setup(configfile)
    upstream = config.get_koji_session("upstream")
    tag = upstream.info["tag"]
    pkgutil = PackageHelper()

    t = pkgutil.is_available(upstream, tag, pkg)
    print(f"Package {pkg} is available under tag {t}")
    if t is not None and t != tag:
        tag = t
    print(pkgutil.is_noarch(upstream, tag, pkg))


if __name__ == "__main__":
    configfile = "config.yaml"
    if len(sys.argv) < 2:
        print("Package name required as argument!")
        sys.exit(1)
    pkg = sys.argv[1]
    print(pkg)
    main(configfile, pkg)
