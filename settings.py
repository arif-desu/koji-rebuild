import os
import yaml

class Data: 
    config = {}
    target: str
    tag: str
    arches: list
    pkg_import = {}
    files = {}
    def __init__(self, configfile) -> None:

        def resolvepath(path):
            """Resolves variables like ${userHome} and ${cwd} in a given path."""
            if path is None:
                return None
            
            variables = {
                "${userHome}": os.path.expanduser("~"),
                "${cwd}": os.getcwd()
            }

            while "${" in path:
                start_idx = path.find("${")
                end_idx = path.find("}", start_idx)
                variable = path[start_idx : end_idx + 1]
                if variable in variables:
                    path = path.replace(variable, variables[variable])
                else:
                    raise ValueError(f"Unknown variable: {variable}")

            return path
        
        with open(configfile, "r") as f:
            parameters = yaml.safe_load(f)

        self.config['upstream'] = resolvepath(parameters['configfile']['upstream'])
        self.config['downstream'] = resolvepath(parameters['configfile']['downstream'])

        self.target = parameters['build_target']['target']
        self.tag = parameters['build_target']['dest_tag']

        self.arches = parameters['arches']

        self.pkg_import['topurl'] = parameters['pkg_import']['topurl']
        self.pkg_import['dir'] = parameters['pkg_import']['dir']


        self.files['build'] = resolvepath(parameters['files']['build'])
        self.files['ignore'] = resolvepath(parameters['files']['ignore'])
        self.files['comps'] = resolvepath(parameters['files']['comps'])
        self.files['log'] = resolvepath(parameters['files']['log'])



data = None

