from .session import KojiSession
from .tasks import TaskState, TaskWatcher
from .package import PackageHelper
from .configuration import Configuration
import logging
from .util import nestedseek, error
from enum import IntEnum
import koji
import asyncio


class BuildState(IntEnum):
    OPEN = 0
    COMPLETE = 1
    DELETED = 2
    FAILED = 3
    CANCELLED = 4


class Rebuild:
    logger = logging.getLogger("rebuild")

    def __init__(self, upstream: KojiSession, downstream: KojiSession) -> None:
        try:
            self.settings = Configuration().settings
        except AttributeError:
            error("Configuration not initialized!")
        self.upstream = upstream
        self.downstream = downstream
        self.tag_up = upstream.instance["tag"]
        self.tag_down = downstream.instance["tag"]
        self.fasttrack = self.settings["package_builds"]["fasttrack"]
        self.pkgutil = PackageHelper()

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
        pkgpath = await self.pkgutil.retrieveRPMs(self.upstream, self.tag_up, pkg)

        if pkgpath:
            task_import = asyncio.create_task(
                asyncio.to_thread(
                    self.pkgutil.import_package, self.downstream, pkgpath, self.tag_down
                )
            )
            ret = await task_import
            result = BuildState.FAILED if ret else BuildState.COMPLETE
        else:
            result = BuildState.FAILED

        if result == BuildState.FAILED:
            self.logger.info(f"Failed to import package {pkg}")
        return result

    async def build_with_scm(self, pkg):
        result = BuildState.OPEN
        task_id = -1
        scmurl = self.pkgutil.getSCM_URL(self.upstream, self.tag_up, pkg)

        if scmurl is not None:
            task_id = self.downstream.build(
                src=scmurl, target=self.downstream.instance["target"]
            )
            task_watcher = TaskWatcher(self.downstream, task_id)
            res = await task_watcher.watch_task()

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

        tag = self.pkgutil.is_available(self.upstream, self.tag_up, pkg)

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
            if self.pkgutil.is_noarch(self.upstream, self.tag_up, pkg):
                self.logger.info(f"Attempting to import package {pkg}")
                try:
                    result = await self.fetch_pkg(pkg)
                    return (pkg, task_id, result)
                except TimeoutError:
                    self.logger.exception(f"Timed out while fetching package {pkg}")
                    return (pkg, task_id, BuildState.FAILED)

        self.logger.info(f"Building package {pkg}")

        response = await self.build_with_scm(pkg)
        return response
