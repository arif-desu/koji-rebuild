import os
import sys
import logging
import configparser
import inspect


def whoami():
    return inspect.stack()[1][3]


"""---------------------------------------------------------------------------------------------"""


def whoiscaller():
    return inspect.stack()[2][3]


"""---------------------------------------------------------------------------------------------"""


class GenericException(Exception):
    def __init__(self, message):
        self.message = message
        super().__init__(message)

    def __str__(self):
        return f"{self.message}"


def error(msg: str, info: bool = False):
    logger = logging.getLogger(whoiscaller())
    if msg is not None:
        logger.error(msg, exc_info=info)
        sys.stderr.write(msg + "\n")

    raise GenericException(msg)


"""---------------------------------------------------------------------------------------------"""


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


"""---------------------------------------------------------------------------------------------"""


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


"""---------------------------------------------------------------------------------------------"""


def resolvepath(path: str) -> str:
    """Resolves relative path specified as environment variable."""
    path = os.path.expanduser(path)

    path = os.path.expandvars(path)

    return path


"""---------------------------------------------------------------------------------------------"""
