from tasks import watch_task, TaskState
import logging
from util import download_rpms, error, nestedseek
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
        try:
            self.try_import = True if os.getenv("IMPORT_ATTEMPT") == "True" else False
        except EnvironmentError:
            self.try_import = False

    def _is_pkg_available_upstream(self, pkg):
        builds = self.upstream.getLatestRPMS(self.tag_up, pkg)
        return False if (not any(builds)) else True

    def _nvr_clash(self, pkg):
        builds = self.upstream.getLatestRPMS(self.tag_up, pkg)
        if any(builds):
            nvr = list(nestedseek(builds, "nvr"))[0]
        else:
            nvr = None
        if nvr is not None:
            builds = self.downstream.getBuild(nvr)
            if not any(builds):
                return False
            else:
                status = list(nestedseek(builds, "state"))
                if any(status) and status[0] == BuildState.COMPLETE:
                    return True
                else:
                    return False
        else:
            return False

    # FIXME: Check login
    async def _import_pkg(self, pkg):
        try:
            topurl = os.getenv("IMPORT_TOPURL")
            download_dir = os.getenv("IMPORT_DIR")
        except EnvironmentError:
            error("Error importing package", exc_info=True)

        pkgpath = None

        # download package rpms from upstream
        pkgpath = await download_rpms(
            topurl, download_dir, self.upstream, self.tag_up, pkg
        )
        if pkgpath:
            self.downstream.importPackage(pkgpath, self.tag_down, pkg)
            result = BuildState.COMPLETE
            self.logger.info(f"Successfully imported package {pkg}")
        else:
            result = BuildState.FAILED
            self.logger.info(f"Failed to import package {pkg}")
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
        result: BuildState = BuildState.BUILDING
        self.logger.info(f"Attempting to build package {pkg}")

        if not self._is_pkg_available_upstream(pkg):
            self.logger.critical(f"Package: {pkg} is unavailable")
            return (pkg, task_id, BuildState.FAILED)

        if self._nvr_clash(pkg):
            self.logger.info(f"Package {pkg} is already built")
            return (pkg, task_id, BuildState.COMPLETE)

        if self.try_import:
            if self.upstream.is_pkg_noarch(self.tag_up, pkg):
                result = await self._import_pkg(pkg)
                return (pkg, task_id, result)

        task_id, result = await self.build_with_scm(pkg)

        return (pkg, task_id, result)
