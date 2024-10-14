import os
import yaml
from util import resolvepath, error
import sys

class Settings:
    instance = dict()
    pkg_import = dict()
    files = dict()

    def __init__(self, configfile) -> None:

        with open(configfile, "r") as f:
            parameters = yaml.safe_load(f)

        self.instance['upstream'] = parameters['instance']['upstream']
        self.instance['downstream'] = parameters['instance']['downstream']

        self.pkg_import['attempt'] = parameters['pkg_import']['attempt']
        self.pkg_import['topurl'] = parameters['pkg_import']['topurl']
        self.pkg_import['dir'] = parameters['pkg_import']['dir']

        self.files['buildlist'] = resolvepath(parameters['files']['buildlist'])
        self.files['ignorelist'] = resolvepath(parameters['files']['ignorelist'])
        self.files['comps'] = resolvepath(parameters['files']['comps'])
        self.files['log'] = resolvepath(parameters['files']['log'])



try:
    settings = Settings("config.yml")
except FileNotFoundError:
    try:
        settings = Settings(sys.argv[2])
    except IndexError:
        error("Configuration file not provided!")
