from .kojisession import KojiSession
from .tasks import watch_task, TaskState
import logging
from .util import download_rpms, nestedseek
from enum import IntEnum
import os
import koji


class BuildState(IntEnum):
    BUILDING = 0
    COMPLETE = 1
    DELETED = 2
    FAILED = 3
    CANCELLED = 4


class Rebuild:
    def __init__(
        self, upstream: KojiSession, downstream: KojiSession, pkgimport: bool = False
    ) -> None:
        self.upstream = upstream
        self.downstream = downstream
        self.tag_up = upstream.info["tag"]
        self.tag_down = downstream.info["tag"]
        self.logger = logging.getLogger("rebuild")
        self.pkgimport = pkgimport

        try:
            if self.downstream.getSessionInfo() is None:
                self.downstream.auth_login()
        except koji.GenericError:
            raise

    def _is_pkg_available_upstream(self, pkg):
        builds = self.upstream.getLatestRPMS(self.tag_up, pkg)
        if any(builds):
            return True
        else:
            inherit = self.upstream.getInheritanceData(tag=self.tag_up)
            parent = list(nestedseek(inherit, "name"))[0]
            if not any(parent):
                return False
            else:
                builds = self.upstream.getLatestRPMS(parent, pkg)

            if not any(builds):
                return False
            else:
                self.logger.info(
                    f"Package is available under parent tag. Switching to tag {parent} for package {pkg}"
                )
                self.tag_up = parent
                return True

    def _nvr_clash(self, pkg):
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

    async def _import_pkg(self, pkg):
        topurl = os.getenv(
            "IMPORT_TOPURL", "https://kojipkgs.fedoraproject.org/packages"
        )
        download_dir = os.getenv("IMPORT_DIR", "~/.rpms")

        pkgpath = None

        # download package rpms from upstream
        pkgpath = await download_rpms(
            topurl, download_dir, self.upstream, self.tag_up, pkg
        )
        if pkgpath:
            ret = self.downstream.importPackage(pkgpath, self.tag_down, pkg)
            result = BuildState.COMPLETE if ret else BuildState.FAILED
        else:
            result = BuildState.FAILED
            self.logger.critical(f"Failed to import package {pkg}")
        return result

    async def build_with_scm(self, pkg):
        result = BuildState.FAILED
        task_id = -1
        scmurl = self.upstream.getSCM_URL(self.tag_up, pkg)

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
        result: BuildState = BuildState.BUILDING
        self.logger.info(f"Attempting to build package {pkg}")

        if not self._is_pkg_available_upstream(pkg):
            self.logger.critical(
                f"Package: {pkg} is unavailable under tag {self.tag_up}"
            )
            return (pkg, task_id, BuildState.FAILED)

        if not self.downstream.checkTagPackage(self.tag_down, pkg):
            self.downstream.packageListAdd(
                taginfo=self.tag_down,
                pkginfo=pkg,
                owner=self.downstream.getLoggedInUser()["name"],
            )

        if self._nvr_clash(pkg):
            self.logger.info(f"Package {pkg} is already built")
            return (pkg, task_id, BuildState.COMPLETE)

        if self.pkgimport:
            if self.upstream.is_pkg_noarch(self.tag_up, pkg):
                try:
                    result = await self._import_pkg(pkg)
                    return (pkg, task_id, result)
                except TimeoutError:
                    self.logger.critical("Failed to import package. Trying to build")
                    pass

        response = await self.build_with_scm(pkg)
        return response
