import koji
import os
import logging
from .util import conf_to_dict, error, resolvepath
from .configuration import Configuration


class KojiSession(koji.ClientSession):
    logger = logging.getLogger("kojisession")

    def __init__(self, instance: str):
        """Initialize a koji session object
        @param: instance - Koji instance name as described in YAML config
        """
        try:
            self.settings = Configuration().settings
        except AttributeError:
            error("Configuration uninitialized!")

        try:
            self.instance = self.settings["instance"][instance]
        except KeyError:
            self.logger.info(f"Undefined instance name {instance} in configfile")
            error(f"Undefined Instance {instance}")

        try:
            configfile = resolvepath(self.instance["kojiconf"])
            self.config = conf_to_dict(str(configfile))
        except FileNotFoundError:
            error(f"File not found {configfile}")  # type: ignore

        try:
            self.server = str(self.config["server"])
        except KeyError:
            error("Parameter server not defined in %s" % configfile)  # type: ignore

        try:
            self.auth = str(self.config["authtype"]).lower()
        except KeyError:
            self.auth = None

        # Call parent class constructor
        super().__init__(baseurl=self.server)

    """-----------------------------------------------------------------------------------------------------------"""

    def _setup_auth(self):
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
            self.logger.warning(f'Unsupported authentication method "{self.auth}"')
            self.certs_set = False

    def auth_login(self) -> bool:
        """Login to koji instance using SSL or Keberos authentication"""
        self._setup_auth()

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

    def get_total_hosts(self, arch: list | None = None):
        """Get total number of hosts available for a specified architecture(s)"""
        return len(self.listHosts(arches=arch, enabled=True, channelID="default"))

    """-----------------------------------------------------------------------------------------------------------"""

    def get_ready_hosts(self, arch: list | None = None):
        """Get number of hosts for specified architecture(s) that are ready to take build job"""
        return len(
            self.listHosts(arches=arch, enabled=True, ready=True, channelID="default")
        )
