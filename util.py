import os
import sys
import logging
import configparser
import aiohttp
import inspect
import settings
import koji

def whoami():
    return inspect.stack()[1][3]

"""-----------------------------------------------------------------------------------------------------------"""

def whoiscaller():
    return inspect.stack()[2][3]

"""-----------------------------------------------------------------------------------------------------------"""

def error(msg = None, code = 1, exc_info:bool = False):
    logger = logging.getLogger(whoiscaller())
    if msg is not None:
        logger.error(msg, exc_info=exc_info)
        sys.stderr.write(msg+"\n")
    sys.exit(code)

"""-----------------------------------------------------------------------------------------------------------"""

def warn(msg = None, exc_info:bool = False):
    logger = logging.getLogger(whoiscaller())
    if msg is not None:
        logger.warning(msg, exc_info=exc_info)
        sys.stderr.write(msg+"\n")
        
"""-----------------------------------------------------------------------------------------------------------"""

def config_to_dict(configfile, section = None):
    logger = logging.getLogger(whoami())

    config = configparser.RawConfigParser()
    try :
        f = os.path.expanduser(configfile) 
        config.read_file(open(f))
    except (FileNotFoundError, PermissionError, configparser.ParsingError) as e:
        error(msg=e, exc_info=True)

    if section is None:
        warn("Section name not specified, trying to figure section from file name : %s" % os.path.basename(configfile))
        try :
            section = os.path.basename(configfile)
            section = section.split(".")[0]
            logger.info("Parsing section %s" % section)
        except (IndexError, ValueError) as e:
            error("Unexpected file name!  Expected - <config_file>.conf", exc_info=True)

    try :
        return dict(config.items(section))
    except configparser.NoSectionError:
       error("No section %s in file %s!" % section, configfile)

"""-----------------------------------------------------------------------------------------------------------"""

def nestedseek(node, key):
    """
    Seek for a value in a nested data structure
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

async def downloadRPMs(session, tag, pkg):
    logger = logging.getLogger(whoami())
    pkgpath = '/'.join([settings.data.pkg_import['dir'], pkg])

    if not os.path.exists(pkgpath):
        try:
            os.makedirs(pkgpath, exist_ok=True)
        except PermissionError:
            logger.error(f"Permission error creating directory {pkgpath}")
            raise
    
    """----------------------------------------------------------"""
    def nvraGenerator(tag, pkg):
        try:
            info = session.getLatestRPMS(tag = tag, package = pkg)
        except koji.GenericError as e:
            logger.critical(str(e).splitlines()[-1])
            return None

        if any(info):
            name = nestedseek(info, 'name')
            version = nestedseek(info, 'version')
            release = nestedseek(info, 'release')
            arch = nestedseek(info, 'arch')
            
            for (n, v, r, a) in zip(name, version, release, arch):
                yield (n, v, r, a)
        else:
            return None
    """----------------------------------------------------------"""
    async def urlretrieve_async(url, filepath):
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                try :
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
            pkgname = '%s-%s-%s.%s.rpm' % (n,v,r,a)
            url = '/'.join([settings.data.pkg_import['topurl'], pkg, v, r, a, pkgname])
            filepath = '/'.join([pkgpath, pkgname])
            await urlretrieve_async(url, filepath)
    
        return pkgpath
    else:
        return None
    
"""-----------------------------------------------------------------------------------------------------------"""

def bootstrap(session):
    logger = logging.getLogger(whoami())
    if session.getSessionInfo() is None:
        if session.login() == False:
            error("You need to be logged into create tags and target!")

    tag = settings.data['tag']
    target = settings.data['target']
    arch = settings.data['arches']
    
    build_tag = "-".join([tag, "build"])
    upd_tag = "-".join([tag, "updates"])
    upd_cand_tag = "-".join([upd_tag, "candidate"])

    try:
        session.createTag(name = tag)
        session.createTag(name = upd_tag, parent = tag)
        session.createTag(name = build_tag, parent = upd_tag, arches = arch)
        session.createTag(name = upd_cand_tag, parent = upd_tag)
        session.createBuildTarget(name = target, build_tag = build_tag, dest_tag = (upd_tag+"-candidate"))
        session.createBuildTarget(name = (target+"-candidate"), build_tag = build_tag, dest_tag = (upd_tag+"-candidate"))
    except koji.GenericError as e:
        warn("Error creating tags and target: %s" % str(e).splitlines()[-1])

    logger.info("Created tags %s, %s, %s, %s" % (tag, build_tag, upd_tag, upd_cand_tag))