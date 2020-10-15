import configparser
import logging
import os
import sys
from pprint import pformat

import progressbar

from . import progname
from .cli import loglevels, get_workspace_argparser, get_resource_argparser, get_storage_argparser, get_root_argparser
from .workspace import Workspace

#: :obj:`str` :
#: Default configuration
defaults = """
[configuration]
characterSet = ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz

[workspace]
rootPath = ./
correctedPath = corrected/
goldPath = gold/
originalPath = original/
trainingPath = training/
nheaderlines = 0
language = Danish
docInfoBaseURL = 

[resources]
resourceRootPath = ./resources/
correctionTrackingFile = correction_tracking.json
dictionaryFile = dictionary.txt
hmmParamsFile = hmm_parameters.json
memoizedCorrectionsFile = memoized_corrections.json
multiCharacterErrorFile = multicharacter_errors.json
reportFile = report.txt
heuristicSettingsFile = settings.json

[storage]
type = fs
db_driver = 
db_host =
db_user =
db_pass =
db_name =

[server]
host = 127.0.0.1
auth_endpoint = 
auth_header = 
"""


class EnvOverride(configparser.BasicInterpolation):
	"""
	This class overrides the .ini file with environment variables if they exist.
	
	They are checked according to this format: CORRECTOCR_<section>_<key>, all upper case.
	
	Thus, to override the storage:db_server setting, set the CORRECTOCR_STORAGE_DB_SERVER variable.
	"""

	def before_get(self, parser, section, option, value, defaults):
		#print([parser, section, option, value, defaults])
		env_var_name = f'CORRECTOCR_{section}_{option}'.upper()
		#print(env_var_name)
		env_var_value = os.path.expandvars(env_var_name)
		if env_var_value in os.environ:
			return os.environ[env_var_value]
		else:
			return super().before_get(parser, section, option, value, defaults)


def setup(configfiles, args):
	progressbar.streams.wrap_stderr()

	config = configparser.RawConfigParser(interpolation=EnvOverride())
	config.optionxform = lambda option: option
	config.read_string(defaults)
	config.read(configfiles, encoding='utf-8')

	# parse global args

	workspaceparser = get_workspace_argparser()
	workspaceparser.set_defaults(**dict(config.items('workspace')))
	(workspaceconfig, args) = workspaceparser.parse_known_args(args)

	resourceparser = get_resource_argparser()
	resourceparser.set_defaults(**dict(config.items('resources')))
	(resourceconfig, args) = resourceparser.parse_known_args(args)

	storageparser = get_storage_argparser()
	storageparser.set_defaults(**dict(config.items('storage')))
	(storageconfig, args) = storageparser.parse_known_args(args)
	storageconfig.trainingPath = workspaceconfig.trainingPath

	# parse the remaining args according to chosen command

	rootparser = get_root_argparser(dict(config.items('configuration')), dict(config.items('server')))
	args = rootparser.parse_args(args)

	logging.basicConfig(
		stream=sys.stdout,
		format='%(asctime)s - %(levelname)8s - %(name)s - %(message)s',
		level=loglevels[args.loglevel],
	)
	log = logging.getLogger(progname)

	log.info(f'Configuration for this invocation:\n{pformat(vars(args))}')

	workspace = Workspace(workspaceconfig, resourceconfig, storageconfig)

	return workspace, args