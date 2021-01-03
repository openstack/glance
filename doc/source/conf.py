# Copyright (c) 2010 OpenStack Foundation.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Glance documentation build configuration file

import os
import sys

# If extensions (or modules to document with autodoc) are in another directory,
# add these directories to sys.path here. If the directory is relative to the
# documentation root, use os.path.abspath to make it absolute, like shown here.
sys.path.insert(0, os.path.abspath('../..'))
sys.path.insert(0, os.path.abspath('../../bin'))

# -- General configuration ---------------------------------------------------

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom ones.
extensions = [
    'stevedore.sphinxext',
    'sphinx.ext.viewcode',
    'oslo_config.sphinxext',
    'oslo_config.sphinxconfiggen',
    'oslo_policy.sphinxext',
    'oslo_policy.sphinxpolicygen',
    'openstackdocstheme',
    'sphinxcontrib.apidoc',
]

# openstackdocstheme options
openstackdocs_repo_name = 'openstack/glance'
openstackdocs_bug_project = 'glance'
openstackdocs_bug_tag = 'documentation'

# sphinxcontrib.apidoc options
apidoc_module_dir = '../../glance'
apidoc_output_dir = 'contributor/api'
apidoc_excluded_paths = [
    'hacking/*',
    'hacking',
    'tests/*',
    'tests',
    'db/sqlalchemy/*',
    'db/sqlalchemy']
apidoc_separate_modules = True

config_generator_config_file = [
    ('../../etc/oslo-config-generator/glance-api.conf',
     '_static/glance-api'),
    ('../../etc/oslo-config-generator/glance-cache.conf',
     '_static/glance-cache'),
    ('../../etc/oslo-config-generator/glance-manage.conf',
     '_static/glance-manage'),
    ('../../etc/oslo-config-generator/glance-scrubber.conf',
     '_static/glance-scrubber'),
]

policy_generator_config_file = [
    ('../../etc/glance-policy-generator.conf', '_static/glance'),
]

# The master toctree document.
master_doc = 'index'

# General information about the project.
copyright = '2010-present, OpenStack Foundation.'

exclude_patterns = [
    # The man directory includes some snippet files that are included
    # in other documents during the build but that should not be
    # included in the toctree themselves, so tell Sphinx to ignore
    # them when scanning for input files.
    'cli/footer.txt',
    'cli/general_options.txt',
    'cli/openstack_options.txt',
]

# If true, the current module name will be prepended to all description
# unit titles (such as .. function::).
add_module_names = True

# If true, sectionauthor and moduleauthor directives will be shown in the
# output. They are ignored by default.
show_authors = True

# The name of the Pygments (syntax highlighting) style to use.
pygments_style = 'native'

# A list of ignored prefixes for module index sorting.
modindex_common_prefix = ['glance.']

# -- Options for man page output --------------------------------------------

# Grouping the document tree for man pages.
# List of tuples 'sourcefile', 'target', 'title', 'Authors name', 'manual'

man_pages = [
    ('cli/glanceapi', 'glance-api', 'Glance API Server',
     ['OpenStack'], 1),
    ('cli/glancecachecleaner', 'glance-cache-cleaner', 'Glance Cache Cleaner',
     ['OpenStack'], 1),
    ('cli/glancecachemanage', 'glance-cache-manage', 'Glance Cache Manager',
     ['OpenStack'], 1),
    ('cli/glancecacheprefetcher', 'glance-cache-prefetcher',
     'Glance Cache Pre-fetcher', ['OpenStack'], 1),
    ('cli/glancecachepruner', 'glance-cache-pruner', 'Glance Cache Pruner',
     ['OpenStack'], 1),
    ('cli/glancecontrol', 'glance-control', 'Glance Daemon Control Helper ',
     ['OpenStack'], 1),
    ('cli/glancemanage', 'glance-manage', 'Glance Management Utility',
     ['OpenStack'], 1),
    ('cli/glancereplicator', 'glance-replicator', 'Glance Replicator',
     ['OpenStack'], 1),
    ('cli/glancescrubber', 'glance-scrubber', 'Glance Scrubber Service',
     ['OpenStack'], 1)
]


# -- Options for HTML output -------------------------------------------------

# The theme to use for HTML and HTML Help pages.  Major themes that come with
# Sphinx are currently 'default' and 'sphinxdoc'.
# html_theme_path = ["."]
# html_theme = '_theme'
html_theme = 'openstackdocs'

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
html_static_path = ['_static']

# Add any paths that contain "extra" files, such as .htaccess or
# robots.txt.
html_extra_path = ['_extra']

# If false, no module index is generated.
html_use_modindex = True

# If false, no index is generated.
html_use_index = True


# -- Options for LaTeX output ------------------------------------------------

# Grouping the document tree into LaTeX files. List of tuples
# (source start file, target name, title, author,
# documentclass [howto/manual]).
latex_documents = [
    ('index', 'Glance.tex', 'Glance Documentation',
     'Glance Team', 'manual'),
]
