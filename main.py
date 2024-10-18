import os
import sys
import asyncio
import logging
import typing
from kojisession import KojiSession
from rebuild import rebuildPackage, BuildState
from util import error, whoami
import configuration


async def task_dispatcher(upstream, downstream, packages: list):
    logger = logging.getLogger(whoami())

    task_queue = list()

    # XXX: Currently checking only one arch
    arches = (downstream.instance['arches'])[0]

    while packages or task_queue:
        ready = downstream.readyHosts(arches)

        while len(task_queue) < ready:
            build_task = asyncio.create_task(rebuildPackage(upstream, downstream, packages.pop(0)))
            task_queue.append(build_task)

        done, _ = await asyncio.wait(task_queue, return_when=asyncio.FIRST_COMPLETED)

        for task in done:
            result:dict = await task

            pkg = next(iter(result))

            if result[pkg] == BuildState.FAILED:
                logger.critical("Package %s build failed!" % pkg)
            elif result[pkg] == BuildState.CANCELLED:
                logger.info("Package %s build cancelled" % pkg)
            elif result[pkg] == BuildState.COMPLETE:
                logger.info("Package %s build complete" % pkg)

            task_queue.remove(task)



if __name__ == "__main__" :
    try:
        configfile = sys.argv[1]
    except IndexError:
        try:
            configfile = os.path.expanduser("/".join([os.getcwd(), "config.yml"]))
        except FileNotFoundError:
            sys.stderr.write("Configuration file not found! Please provide config file in YAML format!")
            sys.exit(1)

    configuration.setup(configfile)

    logging.basicConfig(filename = os.getenv('logfile'),
                        level = logging.INFO,
                        format='%(asctime)s - %(name)s - %(levelname)s : %(message)s')

    logger = logging.getLogger(__name__)

    upstream = KojiSession(configuration.get_instance('upstream'))
    downstream = KojiSession(configuration.get_instance('downstream'))

    try:
        dest_tag = downstream.instance['tag']
    except KeyError:
        target = downstream.getBuildTarget(downstream.instance['target'])
        dest_tag = target['dest_tag_name']

    try:
        upst_tag = upstream.instance['tag']
    except KeyError:
        target = upstream.getBuildTarget(upstream.instance['target'])
        upst_tag = target['dest_tag_name']

    # Check for an ignorelist
    ignorefile: typing.TextIO | None; ignorelist = list()

    if os.getenv("ignorelist") != 'None':
        try:
            ignorefile = open(str(os.getenv("ignorelist")))
            ignorelist = ignorefile.readlines()
            ignorefile.close()
        except (FileNotFoundError, EnvironmentError):
            ignorefile = ignorelist = None
            logger.warning("Ignorelist was not specified. Bypassing ignore requests")
            pass

    # Check for a buildlist
    buildfile: typing.TextIO ; buildlist: list[str]
    if os.getenv('buildlist') != 'None':
        try:
            buildfile = open(str(os.getenv('buildlist')), "r")
        except FileNotFoundError:
            error(f"File {os.getenv('buildlist')} not found!")
    else:
        buildfile = open("buildlist.txt", "r+")
        for pkg in upstream.getPackageList(upst_tag):
            buildfile.write(pkg + "\n")

    buildlist = buildfile.readlines()  #type: ignore 
    buildfile.close()       #type: ignore                

    # Remove package names from buildlist that are included in ignorelist
    if ignorelist:
        for pkg in ignorelist:
            if pkg in buildlist:
                buildlist.remove(pkg)

    # Create list of packages
    packages = [pkg.strip() for pkg in buildlist]

    # Add packages to downstream koji database
    downstream.auth_login()
    for pkg in packages:
        downstream.packageListAdd(taginfo = dest_tag, pkginfo = pkg, owner = downstream.getLoggedInUser()['name'])

    asyncio.run(task_dispatcher(upstream, downstream, packages))
