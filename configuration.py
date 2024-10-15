import os
import yaml
from util import resolvepath

def setup(configfile: str):
    with open(configfile, "r") as f:
        parameters = yaml.safe_load(f)

    os.environ['import_attempt'] = str(parameters['pkg_import']['attempt'])
    os.environ['import_topurl'] = str(parameters['pkg_import']['topurl'])
    os.environ['import_dir'] = str(parameters['pkg_import']['dir'])
    os.environ['buildlist'] = str(resolvepath(parameters['files']['buildlist']))
    os.environ['ignorelist'] = str(resolvepath(parameters['files']['ignorelist']))
    os.environ['logfile'] = str(resolvepath(parameters['files']['logfile']))



def get_instance(configfile: str, instance: str) -> dict:
    with open(configfile, "r") as f:
        parameters = yaml.safe_load(f)

    return parameters['instance'][instance]
