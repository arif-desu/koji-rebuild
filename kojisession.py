import koji
import os
import time
import string
import random
import logging
import shutil
from util import conf_to_dict, nestedseek, error, resolvepath


class KojiSession(koji.ClientSession):

    def __init__(self, instance: dict):
        """Initialize a koji session object
        @param: instance - dictionary object containing koji instance information
        """
        self.instance = instance
        self.logger = logging.getLogger("kojisession")

        try:
            configfile = resolvepath(instance["config"])
            self.config = conf_to_dict(str(configfile))
        except:
            error(exc_info=True)

        try:
            self.server = str(self.config["server"])
        except KeyError:
            error("Parameter server not defined in %s" % configfile)  # type: ignore

        try:
            self.auth = str(self.config["authtype"]).lower()
        except KeyError:
            self.auth = None

        # Call parent class constructor
        koji.ClientSession.__init__(self, baseurl=self.server)

    """-----------------------------------------------------------------------------------------------------------"""

    def _setup_authentication(self):
        if self.auth is not None:
            if self.auth == "ssl":
                try:
                    self._ca_cert = os.path.expanduser(self.config["serverca"])
                    self._client_cert = os.path.expanduser(self.config["cert"])
                    self.certs_set = True
                except KeyError:
                    self.logger.warning(
                        "SSL certificate info missing for %s" % self.server,
                        exc_info=True,
                    )
                    self.certs_set = False
                except (FileNotFoundError, PermissionError) as e:
                    self.logger.warning(e)
                    self.certs_set = False
            elif self.auth == "kerberos":
                try:
                    self._principal = os.path.expanduser(self.config["principal"])
                    self._keytab = os.path.expanduser(self.config["keytab"])
                    self.certs_set = True
                except KeyError:
                    self.logger.warning(
                        "Kerberos authentication info missing for %s" % self.server,
                        exc_info=True,
                    )
                    self.certs_set = False
                except (FileNotFoundError, PermissionError) as e:
                    self.logger.warning(e)
                    self.certs_set = False
                except TypeError:
                    pass

        else:
            self.logger.warning(
                f'Unsupported authentication method "f{self.auth}" specified!'
            )
            self.certs_set = False

    def auth_login(self) -> bool:
        """Login to koji instance using SSL or Keberos authentication"""
        self._setup_authentication()

        if self.certs_set:
            if self.auth == "ssl":
                response = self.ssl_login(
                    cert=self._client_cert, serverca=self._ca_cert
                )
            elif self.auth == "kerberos":
                response = self.gssapi_login(
                    principal=self._principal, keytab=self._keytab
                )
            else:
                self.logger.critical(
                    'Unsupported authentication method "%s" specified' % self.auth
                )
                return False

            if response is True:
                self.logger.info(
                    "Logged in as %s@%s. Authenticated via %s"
                    % ((self.getLoggedInUser()).get("name"), self.server, self.auth)
                )
            return response
        else:
            return False

    """-----------------------------------------------------------------------------------------------------------"""

    def getSCM_URL(self, tag, pkg):
        build_id = None
        try:
            pkginfo = self.getLatestRPMS(tag=tag, package=pkg)
        except koji.GenericError as e:
            self.logger.error(str(e).splitlines()[-1])
        except IndexError:
            self.logger.critical("No package %s in tag %s" % (pkg, tag))
        else:
            build_id = list(nestedseek(pkginfo, key="build_id"))[0]

        if build_id is not None:
            info = self.getBuild(buildInfo=build_id)
            return info["source"]
        else:
            return None

    """-----------------------------------------------------------------------------------------------------------"""

    def is_pkg_noarch(self, tag, pkg):
        noarch = ["src", "noarch"]
        builds = list()

        try:
            builds = self.getLatestRPMS(tag=tag, package=pkg)
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

    """-----------------------------------------------------------------------------------------------------------"""

    def get_package_list(self, tag):
        res = self.listPackages(tagID=tag)
        if res is not None:
            packages = nestedseek(res, "package_name")
            for pkg in packages:
                yield pkg
        else:
            self.logger.info(f"No package tagged under tag : {tag}")
            return None

    """-----------------------------------------------------------------------------------------------------------"""

    def importPackage(self, pkgdir, tag, prune_dir: bool = True):
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

        if not os.path.exists(pkgdir):
            self.logger.critical(f"Directory {pkgdir} does not exist")
            return 1

        if self.getSessionInfo() is None:
            if self.auth_login() == False:
                self.logger.critical("You must be logged in to import packages")
                return 1

        for rpm in list(os.listdir(pkgdir)):
            localfile = "/".join([pkgdir, rpm])
            serverdir = unique_path("app-import")
            # uploadWrapper - undocumented API
            self.uploadWrapper(localfile=localfile, path=serverdir)
            try:
                self.importRPM(path=serverdir, basename=rpm)
                self.logger.info(f"Imported {rpm}")
            except koji.GenericError as e:
                error("Error importing: %s" % str(e).splitlines()[-1])

        untagged = self.untaggedBuilds()

        # Tag imported packages
        for rpm in untagged:
            self.tagBuildBypass(tag, build=rpm)
            self.logger.info(f"Tagging build {rpm} under {tag}")

        self.logger.info(
            "Successfully imported package : %s" % (os.path.basename(pkgdir))
        )

        # Prune downloads after uploading to save disk space
        if prune_dir:
            try:
                shutil.rmtree(pkgdir)
                self.logger.info(f"Removing directory {pkgdir}")
            except PermissionError:
                self.logger.warning(f"Permission error removing directory {pkgdir}")

        return 0

    """-----------------------------------------------------------------------------------------------------------"""

    def get_total_hosts(self, arch):
        """Get total number of hosts available for a specified architecture"""
        return len(self.listHosts(arches=[arch], enabled=True, channelID="default"))

    """-----------------------------------------------------------------------------------------------------------"""

    def get_ready_hosts(self, arch):
        """Get number of hosts for specified architecture that are ready to take build job"""
        return len(
            self.listHosts(arches=[arch], enabled=True, ready=True, channelID="default")
        )
