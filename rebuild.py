from tasks import watch_task
import logging
from util import error
import koji
from enum import IntEnum


class BuildState(IntEnum):
    BUILDING = 0
    COMPLETE = 1
    DELETED = 2
    FAILED = 3
    CANCELLED = 4


async def rebuildPackage(upstream, downstream, pkg, target, tag = None): 
    logger = logging.getLogger(__name__)

    try : 
        #FIXME : target:str won't be carrying this data
        dest_tag = target['dest_tag_name']
    except IndexError:
        error("Target does not specify a destination tag")

    if tag is None:
        tag = dest_tag
    
    if not downstream.checkTagPackage(tag = tag, pkg = pkg):
        logger.warning(f"No package : {pkg} in {tag} present in downstream. Adding package to {tag}")
        downstream.packageListAdd(tag = tag, pkg = pkg)
        
    if downstream.getSessionInfo() is None:
        if downstream.login() == False:
            error("You need to be logged in to build packages!")
    
    # Check if rpms for given package were built in upstream
    builds = upstream.getLatestRPMS(dest_tag, pkg)
    if not any(builds):
        logger.critical("No rpms built for package : %s in upstream" % pkg)
        return None
    
    # Check if package with same NVR already exists in downstream
    # TODO : Check NVR without src rpm
    b1 = builds[0]
    if b1['arch'] == 'src':
        nvr_up = "-".join([b1['name'], b1['version'], b1['release']])

    try:
        builds = downstream.getLatestRPMS(tag, pkg)
    except koji.GenericError:
        nvr_down = None
    else:
        if any(builds):
            b2 = builds[0]
            if b2['arch'] == 'src':
                nvr_down = "-".join([b2['name'], b2['version'], b2['release']])
        else:
            nvr_down = None
        
    if nvr_up == nvr_down:
        logger.info("Package %s is already built and tagged under %s" % (pkg, tag))
        return BuildState.COMPLETE

    # Check if package is noarch
    if upstream.isNoArch(dest_tag, pkg):
        # download package rpms from upstream
        pkgpath = await upstream.downloadRPMs(dest_tag, pkg)
        if pkgpath is not None:
            # import package rpms to downstream and tag the package under 'tag'
            downstream.importPackage(pkgpath, dest_tag, pkg)
    
    else:
        scmurl = upstream.getSCM_URL(dest_tag, pkg)
        if scmurl is not None:
            task_id = downstream.build(src = scmurl, target = target)
            try:
                build_time = int(upstream.getAverageBuildDuration(package = pkg))
                if build_time > 1800:
                    poll = 3600
            except ValueError:
                poll = 1800
            
            result = await watch_task(downstream, task_id, poll_interval=poll)

        return result