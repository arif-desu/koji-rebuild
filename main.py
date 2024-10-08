from kojisession import KojiSession
import os 
import sys
import asyncio
import logging
from util import (error, whoami, warn, bootstrap)
import settings


async def main():
    logger = logging.getLogger(__name__)

    tag = settings.data["tag"]
    target = settings.data["target"]

    upstream = KojiSession(settings.data.config['upstream'])
    downstream = KojiSession(settings.data.config['downstream'])

    if tag not in upstream.listTags():
        error("Tag: %s does not exist in upstream koji database" % tag)

    # create tag and target in downtream instance
    bootstrap(downstream)
    
    # Check for an ignorelist
    if settings.data.files["ignore"] is not None:
        try:
            ignorelist = open(settings.data.files["ignore"])
        except OSError:
            raise
    else:
        ignorelist = None

    packagelist = open("packages.txt", "w")
    
    # Fetch package names from upstream
    for pkg in upstream.getPackageList(upstream, tag):
        # Write package names to a file
        # TODO : Ignore packages from ignorelist
        packagelist.write(str(pkg) + "\n")

        # Add package to downstream database
        downstream.packageListAdd(tag = tag, pkg = pkg)
    

    ignorelist.close()
    task_queue = list()
    while True:
        try:
            pass
            
        except KeyboardInterrupt:
            sys.stdout.write("Received interrupt signal from input. Exiting...\n")
            break




if __name__ == "__main__" :

    settings.data = settings.Data(sys.argv[1])

    if settings.data.files['log'] is None:
        settings.data.files['log'] = os.getcwd() + "/app.log"

    logging.basicConfig(filename = settings.data.files['log'], 
                        level = logging.INFO, 
                        format='%(asctime)s - %(name)s - %(levelname)s : %(message)s')

    asyncio.run(main)
