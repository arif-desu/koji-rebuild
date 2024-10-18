from tasks import watch_task, TaskState
import logging
from util import error, downloadRPMs
import koji
from enum import IntEnum
import os


class BuildState(IntEnum):
    BUILDING = 0
    COMPLETE = 1
    DELETED = 2
    FAILED = 3
    CANCELLED = 4


async def rebuildPackage(upstream, downstream, pkg: str) -> dict[str, BuildState]:
    logger = logging.getLogger(__name__)

    result = BuildState.FAILED
    upst_tag = None

    try:
        upst_tag = upstream.instance['tag']
    except KeyError:
        target = upstream.getBuildTarget(upstream.instance['target'])
        upst_tag = target['dest_tag_name']

    tag = downstream.instance['tag']

    if not downstream.checkTagPackage(tag = tag, pkg = pkg):
        logger.warning(f"No package : {pkg} associated with {tag}. Adding package to {tag}")
        downstream.packageListAdd(tag = tag, pkg = pkg)

    if downstream.getSessionInfo() is None:
        if downstream.auth_login() == False:
            error("You need to be logged in to build packages!")

    # Check if rpms for given package were built in upstream
    builds = upstream.getLatestRPMS(upst_tag, pkg)

    if not any(builds):
        logger.critical("No rpms built for package : %s in upstream" % pkg)
        return {pkg : BuildState.FAILED}

    # Check if package with same NVR already exists in downstream
    nvr_up = nvr_down = None
    b1 = builds[0][0]
    if b1['arch'] == 'src':
        nvr_up = "-".join([b1['name'], b1['version'], b1['release']])

    try:
        builds = downstream.getLatestRPMS(tag, pkg)
    except koji.GenericError:
        nvr_down = None
    else:
        if any(builds):
            b2 = builds[0][0]
            if b2['arch'] == 'src':
                nvr_down = "-".join([b2['name'], b2['version'], b2['release']])
        else:
            nvr_down = None

    if nvr_up == nvr_down:
        logger.info("Package %s is already built and tagged under %s" % (pkg, tag))
        return {pkg : BuildState.COMPLETE}
    
    attempt_import = False
    if os.getenv('import_attempt') == 'True':
        attempt_import = True

    if attempt_import:
        # Check if package is noarch
        if upstream.isNoArch(upst_tag, pkg):
            # download package rpms from upstream
            pkgpath = await downloadRPMs(os.getenv('import_topurl'), os.getenv('import_dir'), upstream, upst_tag, pkg)
            if pkgpath is not None:
                # import package rpms to downstream and tag the package under 'tag'
                downstream.importPackage(pkgpath, tag, pkg)
                result = BuildState.COMPLETE
            else:
                result = BuildState.FAILED
            return {pkg : result}

    scmurl = upstream.getSCM_URL(upst_tag, pkg)

    if scmurl is not None:
        task_id = downstream.build(src = scmurl, target = downstream.instance['target'])
        res = await watch_task(downstream, task_id)

        if res == TaskState.CLOSED:
            result = BuildState.COMPLETE
        elif res == TaskState.CANCELLED:
            result = BuildState.CANCELLED
        elif res == TaskState.FAILED:
            result = BuildState.FAILED

    return {pkg : result}
        
    
