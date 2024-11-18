from tasks import watch_task, TaskState
import logging
from util import download_rpms, nestedseek
from enum import IntEnum
import os


class BuildState(IntEnum):
    BUILDING = 0
    COMPLETE = 1
    DELETED = 2
    FAILED = 3
    CANCELLED = 4


class Rebuild:
    def __init__(self, upstream, downstream) -> None:
        self.upstream = upstream
        self.downstream = downstream
        self.tag_up = upstream.instance["tag"]
        self.tag_down = downstream.instance["tag"]
        self.logger = logging.getLogger(__name__)

    def __check_pkg_status(self, pkg):
        builds = self.upstream.getLatestRPMS(self.tag_up, pkg)
        return False if (not any(builds)) else True

    def _is_pkg_built_previously(self, pkg):
        builds = self.upstream.getLatestRPMS(pkg)
        if any(builds):
            nvr = list(nestedseek(builds, "nvr"))[0]
        else:
            nvr = None
        if nvr is not None:
            if self.downstream.getBuild(nvr) is None:
                return False
            else:
                return True
        else:
            return False

    # FIXME: Check login
    async def __try_import(self, pkg):
        try:
            topurl = os.getenv("IMPORT_TOPURL")
            download_dir = os.getenv("IMPORT_DIR")
        except EnvironmentError:
            return False

        pkgpath = None

        # download package rpms from upstream
        pkgpath = await download_rpms(
            topurl, download_dir, self.upstream, self.tag_up, pkg
        )
        if pkgpath:
            self.downstream.importPackage(pkgpath, self.tag_down, pkg)
            result = BuildState.COMPLETE
        else:
            result = BuildState.FAILED
        return result

    async def build_with_scm(self, pkg):
        result = BuildState.FAILED
        task_id = -1
        scmurl = self.upstream.getSCM_URL(self.tag_up, pkg)

        if scmurl is not None:
            task_id = self.downstream.build(
                src=scmurl, target=self.downstream.instance["target"]
            )
            res = await watch_task(self.downstream, task_id)

            if res == TaskState.CLOSED:
                result = BuildState.COMPLETE
            elif res == TaskState.CANCELLED:
                result = BuildState.CANCELLED
            elif res == TaskState.FAILED:
                result = BuildState.FAILED

        return (task_id, result)

    async def rebuild_package(self, pkg) -> tuple[str, int, int]:
        task_id = -1
        if not self.__check_pkg_status(pkg):
            return (pkg, task_id, BuildState.FAILED)

        if self._is_pkg_built_previously(pkg):
            return (pkg, task_id, BuildState.COMPLETE)

        attempt_import = True if os.getenv("IMPORT_ATTEMPT") == "True" else False

        if attempt_import and self.upstream.is_pkg_noarch(self.tag_up, pkg):
            result = await self.__try_import(pkg)
        else:
            task_id, result = await self.build_with_scm(pkg)

        return (pkg, task_id, result)
