from .configuration import Configuration
from .session import KojiSession
from .util import nestedseek
import koji
import logging
import time
import os
import string
import random
import shutil
import aiohttp


class PackageHelper:
    def __init__(self) -> None:
        self.logger = logging.getLogger("PackageHelper")

    def getSCM_URL(self, session: KojiSession, tag: str, pkg: str):
        build_id = None
        try:
            pkginfo = session.getLatestRPMS(tag=tag, package=pkg)
        except koji.GenericError as e:
            self.logger.error(str(e).splitlines()[-1])
        except IndexError:
            self.logger.critical("No package %s associated with tag %s" % (pkg, tag))
        else:
            build_id = list(nestedseek(pkginfo, key="build_id"))[0]

        if build_id is not None:
            info = session.getBuild(buildInfo=build_id)
            return info["source"]
        else:
            return None

    def is_noarch(self, session: KojiSession, tag: str, pkg: str):
        noarch = ["src", "noarch"]
        builds = list()

        try:
            builds = session.getLatestRPMS(tag=tag, package=pkg)
        except koji.GenericError as e:
            self.logger.warning(str(e).splitlines()[-1])

        if any(builds):
            arches = nestedseek(builds, key="arch")
            for arch in arches:
                if str(arch) not in noarch:
                    return False

            return True
        else:
            self.logger.critical("No builds for package %s" % pkg)
            return False

    def get_package_list(self, session: KojiSession, tag: str) -> None | list[str]:
        res = session.listPackages(tagID=tag)
        if res is not None:
            packages = list(nestedseek(res, "package_name"))
            return packages
        else:
            self.logger.info(f"No package tagged under tag : {tag}")
            return None

    async def retrieveRPMs(self, session: KojiSession, tag: str, pkg: str):
        """
        Retrieves RPM packages from server
        :param: session - KojiSession object
        :param: tag - tag reference for package
        :param: pkg - package to be downloaded
        :return - path to package download directory
        """
        settings = Configuration().settings
        dir = settings["package_builds"]["download_dir"]
        topurl = settings["package_builds"]["topurl"]
        pkgpath = "/".join([dir, pkg])

        if not os.path.exists(pkgpath):
            try:
                os.makedirs(pkgpath, exist_ok=True)
            except PermissionError:
                self.logger.error(f"Permission error creating directory {pkgpath}")
                raise

        def nvra_generator(tag, pkg):
            try:
                info = session.getLatestRPMS(tag=tag, package=pkg)
            except koji.GenericError as e:
                self.logger.critical(str(e).splitlines()[-1])
                return None

            if any(info):
                name = nestedseek(info, "name")
                version = nestedseek(info, "version")
                release = nestedseek(info, "release")
                arch = nestedseek(info, "arch")

                for n, v, r, a in zip(name, version, release, arch):
                    yield (n, v, r, a)
            else:
                return None

        async def urlretrieve_async(url, filepath):
            timeout = aiohttp.ClientTimeout(total=None, sock_read=5, sock_connect=5)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as response:
                    try:
                        assert response.status == 200
                    except AssertionError:
                        self.logger.error(
                            f"Server response code :{str(response.status)} for package {pkg}. URL - {url}"
                        )
                        return None

                    with open(filepath, "wb") as f:
                        while True:
                            chunk = await response.content.read(1024)
                            if not chunk:
                                break
                            f.write(chunk)

        nvra = nvra_generator(tag, pkg)

        if nvra is not None:
            for i in nvra:
                (n, v, r, a) = i
                pkgname = "%s-%s-%s.%s.rpm" % (n, v, r, a)
                url = "/".join([topurl, pkg, v, r, a, pkgname])
                filepath = "/".join([pkgpath, pkgname])
                await urlretrieve_async(url, filepath)

            return pkgpath
        else:
            return None

    def import_package(self, session: KojiSession, pkgdir, tag, prune_dir: bool = True):
        """Download and import package to koji instance
        :param pkgdir: str - Path to directory where packages are downloaded
        :param tag: str - Tag name under which package will be tagged
        :param prune_dir: bool - If pkgdir should be deleted to save disk space
        """

        def unique_path(prefix):
            """Create a unique path fragment by appending a path component to prefix."""
            return "%s/%r.%s" % (
                prefix,
                time.time(),
                "".join([random.choice(string.ascii_letters) for _ in range(8)]),
            )

        def prune():
            try:
                shutil.rmtree(pkgdir)
                self.logger.info(f"Removing directory {pkgdir}")
            except PermissionError:
                self.logger.warning(f"Permission error removing directory {pkgdir}")

        if not os.path.exists(pkgdir):
            self.logger.critical(f"Directory {pkgdir} does not exist")
            return 1

        if session.getSessionInfo() is None:
            if not session.auth_login():
                self.logger.critical("You must be logged in to import packages")
                return 1

        for rpm in list(os.listdir(pkgdir)):
            localfile = "/".join([pkgdir, rpm])
            serverdir = unique_path("app-import")
            # uploadWrapper - undocumented API
            session.uploadWrapper(localfile=localfile, path=serverdir)
            try:
                session.importRPM(path=serverdir, basename=rpm)
                self.logger.info(f"Imported {rpm}")
            except koji.GenericError as e:
                self.logger.error(
                    f"Error importing package {os.path.basename(pkgdir)}: {str(e).splitlines()[-1]}"
                )
                prune()
                return -1

        untagged = session.untaggedBuilds()

        # Tag imported packages
        for rpm in untagged:
            session.tagBuildBypass(tag, build=rpm)
            self.logger.info(f"Tagging build {rpm} under {tag}")

        self.logger.info(f"Successfully imported package : {os.path.basename(pkgdir)}")

        # Prune downloads after uploading to save disk space
        if prune_dir:
            prune()

        return 0

    def is_available(self, session: KojiSession, tag: str, pkg: str):
        builds = session.getLatestRPMS(tag, pkg)
        if any(builds):
            return tag
        else:
            inherit = session.getInheritanceData(tag=tag)
            parent = list(nestedseek(inherit, "name"))[0]
            if not any(parent):
                return None
            else:
                builds = session.getLatestRPMS(parent, pkg)

            if not any(builds):
                return None
            else:
                self.logger.info(
                    f"Package is available under parent tag. Switching to tag {parent} for package {pkg}"
                )
                tag = parent
                return tag
