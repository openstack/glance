# Copyright 2015 Intel Corporation
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import os
import re
import shutil
import tarfile
import urllib

try:
    from defusedxml import cElementTree as ET
except ImportError:
    from defusedxml import ElementTree as ET

from oslo_config import cfg
from oslo_log import log as logging
from oslo_serialization import jsonutils as json
from taskflow.patterns import linear_flow as lf
from taskflow import task

from glance.i18n import _, _LW

LOG = logging.getLogger(__name__)

CONF = cfg.CONF
# Define the CIM namespaces here. Currently we will be supporting extracting
# properties only from CIM_ProcessorAllocationSettingData
CIM_NS = {'http://schemas.dmtf.org/wbem/wscim/1/cim-schema/2/'
          'CIM_ProcessorAllocationSettingData': 'cim_pasd'}


class _OVF_Process(task.Task):
    """
    Extracts the single disk image from an OVA tarball and saves it to the
    Glance image store. It also parses the included OVF file for selected
    metadata which it then saves in the image store as the previously saved
    image's properties.
    """

    default_provides = 'file_path'

    def __init__(self, task_id, task_type, image_repo):
        self.task_id = task_id
        self.task_type = task_type
        self.image_repo = image_repo
        super(_OVF_Process, self).__init__(
            name='%s-OVF_Process-%s' % (task_type, task_id))

    def _get_extracted_file_path(self, image_id):
        file_path = CONF.task.work_dir
        # NOTE(abhishekk): Use reserved 'os_glance_tasks_store' for tasks.
        if CONF.enabled_backends:
            file_path = getattr(
                CONF, 'os_glance_tasks_store').filesystem_store_datadir

        return os.path.join(file_path,
                            "%s.extracted" % image_id)

    def _get_ova_iter_objects(self, uri):
        """Returns iterable object either for local file or uri

        :param uri: uri (remote or local) to the ova package we want to iterate
        """

        if uri.startswith("file://"):
            uri = uri.split("file://")[-1]
            return open(uri, "rb")

        return urllib.request.urlopen(uri)

    def execute(self, image_id, file_path):
        """
        :param image_id: Id to use when storing extracted image to Glance
            image store. It is assumed that some other task has already
            created a row in the store with this id.
        :param file_path: Path to the OVA package
        """

        file_abs_path = file_path.split("file://")[-1]
        image = self.image_repo.get(image_id)
        # Expect 'ova' as image container format for OVF_Process task
        if image.container_format == 'ova':
            # FIXME(dramakri): This is an admin-only feature for security
            # reasons. Ideally this should be achieved by making the import
            # task API admin only. This is one of the items that the upcoming
            # import refactoring work plans to do. Until then, we will check
            # the context as a short-cut.
            if image.context and image.context.is_admin:
                extractor = OVAImageExtractor()
                data_iter = None
                try:
                    data_iter = self._get_ova_iter_objects(file_path)
                    disk, properties = extractor.extract(data_iter)
                    image.extra_properties.update(properties)
                    image.container_format = 'bare'
                    self.image_repo.save(image)
                    dest_path = self._get_extracted_file_path(image_id)
                    with open(dest_path, 'wb') as f:
                        shutil.copyfileobj(disk, f, 4096)
                finally:
                    if data_iter:
                        data_iter.close()

                # Overwrite the input ova file since it is no longer needed
                os.unlink(file_abs_path)
                os.rename(dest_path, file_abs_path)

            else:
                raise RuntimeError(_('OVA extract is limited to admin'))

        return file_path

    def revert(self, image_id, result, **kwargs):
        fs_path = self._get_extracted_file_path(image_id)
        if os.path.exists(fs_path):
            os.path.remove(fs_path)


class OVAImageExtractor(object):
    """Extracts and parses the uploaded OVA package

    A class that extracts the disk image and OVF file from an OVA
    tar archive. Parses the OVF file for metadata of interest.
    """

    def __init__(self):
        self.interested_properties = []
        self._load_interested_properties()

    def extract(self, ova):
        """Extracts disk image and OVF file from OVA package

        Extracts a single disk image and OVF from OVA tar archive and calls
        OVF parser method.

        :param ova: a file object containing the OVA file
        :returns: a tuple of extracted disk file object and dictionary of
            properties parsed from the OVF file
        :raises RuntimeError: an error for malformed OVA and OVF files
        """
        with tarfile.open(fileobj=ova) as tar_file:
            filenames = tar_file.getnames()
            ovf_filename = next((filename for filename in filenames
                                 if filename.endswith('.ovf')), None)
            if ovf_filename:
                ovf = tar_file.extractfile(ovf_filename)
                disk_name, properties = self._parse_OVF(ovf)
                ovf.close()
            else:
                raise RuntimeError(_('Could not find OVF file in OVA archive '
                                     'file.'))

            disk = tar_file.extractfile(disk_name)

            return (disk, properties)

    def _parse_OVF(self, ovf):
        """Parses the OVF file

        Parses the OVF file for specified metadata properties. Interested
        properties must be specified in ovf-metadata.json conf file.

        The OVF file's qualified namespaces are removed from the included
        properties.

        :param ovf: a file object containing the OVF file
        :returns: a tuple of disk filename and a properties dictionary
        :raises RuntimeError: an error for malformed OVF file
        """

        def _get_namespace_and_tag(tag):
            """Separate and return the namespace and tag elements.

            There is no native support for this operation in elementtree
            package. See http://bugs.python.org/issue18304 for details.
            """
            m = re.match(r'\{(.+)\}(.+)', tag)
            if m:
                return m.group(1), m.group(2)
            else:
                return '', tag

        disk_filename, file_elements, file_ref = None, None, None
        properties = {}
        for event, elem in ET.iterparse(ovf):
            if event == 'end':
                ns, tag = _get_namespace_and_tag(elem.tag)
                if ns in CIM_NS and tag in self.interested_properties:
                    properties[CIM_NS[ns] + '_' + tag] = (elem.text.strip()
                                                          if elem.text else '')

                if tag == 'DiskSection':
                    disks = [child for child in list(elem)
                             if _get_namespace_and_tag(child.tag)[1] ==
                             'Disk']
                    if len(disks) > 1:
                        """
                        Currently only single disk image extraction is
                        supported.
                        FIXME(dramakri): Support multiple images in OVA package
                        """
                        raise RuntimeError(_('Currently, OVA packages '
                                             'containing multiple disk are '
                                             'not supported.'))
                    disk = next(iter(disks))
                    file_ref = next(value for key, value in disk.items() if
                                    _get_namespace_and_tag(key)[1] ==
                                    'fileRef')

                if tag == 'References':
                    file_elements = list(elem)

                # Clears elements to save memory except for 'File' and 'Disk'
                # references, which we will need to later access
                if tag != 'File' and tag != 'Disk':
                    elem.clear()

        for file_element in file_elements:
            file_id = next(value for key, value in file_element.items()
                           if _get_namespace_and_tag(key)[1] == 'id')
            if file_id != file_ref:
                continue
            disk_filename = next(value for key, value in file_element.items()
                                 if _get_namespace_and_tag(key)[1] == 'href')

        return (disk_filename, properties)

    def _load_interested_properties(self):
        """Find the OVF properties config file and load it.

        OVF properties config file specifies which metadata of interest to
        extract. Reads in a JSON file named 'ovf-metadata.json' if available.
        See example file at etc/ovf-metadata.json.sample.
        """
        filename = 'ovf-metadata.json'
        match = CONF.find_file(filename)
        if match:
            with open(match, 'r') as properties_file:
                properties = json.loads(properties_file.read())
                self.interested_properties = properties.get(
                    'cim_pasd', [])
                if not self.interested_properties:
                    msg = _LW('OVF metadata of interest was not specified '
                              'in ovf-metadata.json config file. Please '
                              'set "cim_pasd" to a list of interested '
                              'CIM_ProcessorAllocationSettingData '
                              'properties.')
                    LOG.warning(msg)
        else:
            LOG.warning(_LW('OVF properties config file "ovf-metadata.json" '
                            'was not found.'))


def get_flow(**kwargs):
    """Returns task flow for OVF Process.

    :param task_id: Task ID
    :param task_type: Type of the task.
    :param image_repo: Image repository used.
    """
    task_id = kwargs.get('task_id')
    task_type = kwargs.get('task_type')
    image_repo = kwargs.get('image_repo')

    LOG.debug("Flow: %(task_type)s with ID %(id)s on %(repo)s",
              {'task_type': task_type, 'id': task_id, 'repo': image_repo})

    return lf.Flow(task_type).add(
        _OVF_Process(task_id, task_type, image_repo),
    )
