from .session import KojiSession
from .tasks import watch_task, TaskState
from .package import PackageHelper
import logging
from .util import nestedseek
from enum import IntEnum
import os
import koji


class BuildState(IntEnum):
    OPEN = 0
    COMPLETE = 1
    DELETED = 2
    FAILED = 3
    CANCELLED = 4


class Rebuild:
    def __init__(self, upstream: KojiSession, downstream: KojiSession) -> None:
        self.logger = logging.getLogger("rebuild")
        self.upstream = upstream
        self.downstream = downstream
        self.tag_up = upstream.info["tag"]
        self.tag_down = downstream.info["tag"]
        self.fasttrack = bool(int(os.getenv("FAST_TRACK", default="0")))
        self.pkg_util = PackageHelper()

        try:
            if self.downstream.getSessionInfo() is None:
                self.downstream.auth_login()
        except koji.GenericError:
            raise

    def nvr_clash(self, pkg):
        builds = self.upstream.getLatestRPMS(self.tag_up, pkg)
        if any(builds):
            nvr = list(nestedseek(builds, "nvr"))[0]
        else:
            nvr = None
        if nvr is not None:
            builds = self.downstream.getBuild(nvr)
            if builds is not None and not any(builds):
                return False
            else:
                status = list(nestedseek(builds, "state"))
                if any(status) and status[0] == BuildState.COMPLETE:
                    return True
                else:
                    return False
        else:
            return False

    async def fetch_pkg(self, pkg):
        pkgpath = await self.pkg_util.retrieveRPMs(self.upstream, self.tag_up, pkg)

        if pkgpath:
            # TODO: Spawn thread instead of async
            ret = self.pkg_util.import_package(
                self.downstream, pkgpath, self.tag_down, pkg
            )
            result = BuildState.COMPLETE if ret else BuildState.FAILED
        else:
            result = BuildState.FAILED
            self.logger.critical(f"Failed to import package {pkg}")
        return result

    async def build_with_scm(self, pkg):
        result = BuildState.OPEN
        task_id = -1
        scmurl = self.pkg_util.getSCM_URL(self.upstream, self.tag_up, pkg)

        if scmurl is not None:
            task_id = self.downstream.build(
                src=scmurl, target=self.downstream.info["target"]
            )
            res = await watch_task(self.downstream, task_id)

            if res == TaskState.CLOSED:
                result = BuildState.COMPLETE
            elif res == TaskState.CANCELLED:
                result = BuildState.CANCELLED
            elif res == TaskState.FAILED:
                result = BuildState.FAILED

        return (pkg, task_id, result)

    async def rebuild_package(self, pkg) -> tuple[str, int, int]:
        task_id = -1
        result: BuildState = BuildState.OPEN

        tag = self.pkg_util.is_available(self.upstream, self.tag_up, pkg)

        if tag is None:
            self.logger.critical(
                f"Package: {pkg} is unavailable under tag {self.tag_up}"
            )
            return (pkg, task_id, BuildState.FAILED)
        else:
            self.tag_up = tag

        if not self.downstream.checkTagPackage(self.tag_down, pkg):
            self.downstream.packageListAdd(
                taginfo=self.tag_down,
                pkginfo=pkg,
                owner=self.downstream.getLoggedInUser()["name"],
            )

        if self.nvr_clash(pkg):
            self.logger.info(f"Package {pkg} is already built")
            return (pkg, task_id, BuildState.COMPLETE)

        if self.fasttrack:
            if self.pkg_util.is_noarch(self.upstream, self.tag_up, pkg):
                self.logger.info(f"Attempting to import package {pkg}")
                try:
                    result = await self.fetch_pkg(pkg)
                    return (pkg, task_id, result)
                except TimeoutError:
                    raise

        self.logger.info(f"Building package {pkg}")

        response = await self.build_with_scm(pkg)
        return response
