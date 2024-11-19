import os
import sys
import logging
import configparser
from typing import NoReturn
import aiohttp
import inspect
import koji


def whoami():
    return inspect.stack()[1][3]


"""-----------------------------------------------------------------------------------------------------------"""


def whoiscaller():
    return inspect.stack()[2][3]


"""-----------------------------------------------------------------------------------------------------------"""


def error(msg=None, code=1, exc_info: bool = False) -> NoReturn:
    logger = logging.getLogger(whoiscaller())
    if msg is not None:
        logger.error(msg, exc_info=exc_info)
        sys.stderr.write(msg + "\n")
    sys.exit(code)


"""-----------------------------------------------------------------------------------------------------------"""


def warn(msg=None, exc_info: bool = False):
    logger = logging.getLogger(whoiscaller())
    if msg is not None:
        logger.warning(msg, exc_info=exc_info)
        sys.stderr.write(msg + "\n")


"""-----------------------------------------------------------------------------------------------------------"""


def conf_to_dict(configfile: str) -> dict:
    """
    Reads a config file and returns a dictionary. The first declared section is parsed
    @param: configfile(str) - Path to the configuration file

    @return: dict
    """
    logger = logging.getLogger(whoami())

    conf_dict = dict()
    section: str

    config = configparser.RawConfigParser()
    try:
        f = os.path.expanduser(configfile)
        config.read_file(open(f))
    except (FileNotFoundError, PermissionError, configparser.ParsingError) as e:
        logger.exception(e)
        raise e

    try:
        section = config.sections()[0]
    except IndexError:
        section = (os.path.basename(configfile)).split(".")[0]
        raise configparser.NoSectionError(section)

    conf_dict = dict(config.items(section))

    return conf_dict


"""-----------------------------------------------------------------------------------------------------------"""


def nestedseek(node, key):
    """Seek for a value in a nested data structure

    @param: node(dict|list) - Data structure node to parse
    @param: key(int|str) - key/index to search associated value

    @return: Generator
    """
    # check if node is a list
    if isinstance(node, list):
        for i in node:
            for val in nestedseek(i, key):
                yield val

    # check if node is a dictionary
    elif isinstance(node, dict):
        # is key available in the immediate dictionary
        if key in node:
            yield node[key]

        # is key available in a sub-dictionary
        for j in node.values():
            for val in nestedseek(j, key):
                yield val


"""-----------------------------------------------------------------------------------------------------------"""


async def download_rpms(topurl, dir, session, tag, pkg):
    """
    Retrieves RPM packages from server
    @param topurl - rpm
    @param dir - parent directory path to store package rpms
    @param: session - KojiSession object
    @param: tag - tag reference for package
    @param: pkg - package to be downloaded

    @return - path to package download directory
    """
    logger = logging.getLogger(whoami())
    pkgpath = "/".join([dir, pkg])

    if not os.path.exists(pkgpath):
        try:
            os.makedirs(pkgpath, exist_ok=True)
        except PermissionError:
            logger.error(f"Permission error creating directory {pkgpath}")
            raise

    """----------------------------------------------------------"""

    def nvraGenerator(tag, pkg):
        try:
            info = session.getLatestRPMS(tag=tag, package=pkg)
        except koji.GenericError as e:
            logger.critical(str(e).splitlines()[-1])
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

    """----------------------------------------------------------"""

    async def urlretrieve_async(url, filepath):
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                try:
                    assert response.status == 200
                except AssertionError:
                    error("Server response code : %s" % str(response.status))

                with open(filepath, "wb") as f:
                    while True:
                        chunk = await response.content.read(1024)
                        if not chunk:
                            break
                        f.write(chunk)

    """----------------------------------------------------------"""

    nvra = nvraGenerator(tag, pkg)

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


"""-----------------------------------------------------------------------------------------------------------"""


def resolvepath(path):
    """Resolves relative path specified as environment variable."""
    if path is None:
        return None

    variables = {"${HOME}": os.path.expanduser("~"), "${PWD}": os.getcwd()}

    while "${" in path:
        start_idx = path.find("${")
        end_idx = path.find("}", start_idx)
        variable = path[start_idx : end_idx + 1]
        if variable in variables:
            path = path.replace(variable, variables[variable])
        else:
            raise ValueError(f"Unknown variable: {variable}")

    return path
