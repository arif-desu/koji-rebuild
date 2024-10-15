import os
import yaml
from util import resolvepath, error

def setup(configfile: str):
    configfile = os.path.expanduser(configfile)
    with open(configfile, "r") as f:
        parameters = yaml.safe_load(f)

    os.environ['configfile'] = configfile
    os.environ['import_attempt'] = str(parameters['pkg_import']['attempt'])
    os.environ['import_topurl'] = str(parameters['pkg_import']['topurl'])
    os.environ['import_dir'] = str(parameters['pkg_import']['dir'])
    os.environ['buildlist'] = str(resolvepath(parameters['files']['buildlist']))
    os.environ['ignorelist'] = str(resolvepath(parameters['files']['ignorelist']))
    os.environ['logfile'] = str(resolvepath(parameters['files']['logfile']))



def get_instance(name: str) -> dict:
    instance = dict()
    try:
        configfile = str(os.getenv('configfile'))
    except EnvironmentError:
        error('Environment variable "configfile" is not set. Call setup() function')
    else:
        with open(str(configfile), "r") as f:
            parameters = yaml.safe_load(f)
        instance = parameters['instance'][name]
    
    return instance
