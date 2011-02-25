# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011 OpenStack, LLC
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
import shutil
import signal
import subprocess
import tempfile
import time
import unittest


def execute(cmd):
    env = os.environ.copy()
    # Make sure that we use the programs in the
    # current source directory's bin/ directory.
    env['PATH'] = os.path.join(os.getcwd(), 'bin') + ':' + env['PATH']
    process = subprocess.Popen(cmd,
                               shell=True,
                               stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE,
                               env=env)
    result = process.communicate()
    (out, err) = result
    exitcode = process.returncode
    if process.returncode != 0:
        msg = "Command %(cmd)s did not succeed. Returned an exit "\
              "code of %(exitcode)d."\
              "\n\nSTDOUT: %(out)s"\
              "\n\nSTDERR: %(err)s" % locals()
        raise RuntimeError(msg)
    return exitcode, out, err


class TestMiscellaneous(unittest.TestCase):

    """Some random tests for various bugs and stuff"""

    def tearDown(self):
        self._cleanup_test_servers()

    def _cleanup_test_servers(self):
        # Clean up any leftover test servers...
        pid_files = ('glance-api.pid', 'glance-registry.pid')
        for pid_file in pid_files:
            if os.path.exists(pid_file):
                pid = int(open(pid_file).read().strip())
                try:
                    os.killpg(pid, signal.SIGTERM)
                except:
                    pass  # Ignore if the process group is dead
                os.unlink(pid_file)

    def test_exception_not_eaten_from_registry_to_api(self):
        """
        A test for LP bug #704854 -- Exception thrown by registry
        server is consumed by API server.

        We start both servers daemonized.

        We then use curl to try adding an image that does not
        meet validation requirements on the registry server and test
        that the error returned from the API server to curl is appropriate

        We also fire the glance-upload tool against the API server
        and verify that glance-upload doesn't eat the exception either...
        """

        self._cleanup_test_servers()

        # Port numbers hopefully not used by anything...
        api_port = 32001
        reg_port = 32000
        image_dir = "/tmp/test.images.%d" % api_port
        if os.path.exists(image_dir):
            shutil.rmtree(image_dir)

        # A config file to use just for this test...we don't want
        # to trample on currently-running Glance servers, now do we?
        with tempfile.NamedTemporaryFile() as conf_file:
            conf_contents = """[DEFAULT]
verbose = True
debug = True

[app:glance-api]
paste.app_factory = glance.server:app_factory
filesystem_store_datadir=%(image_dir)s
default_store = file
bind_host = 0.0.0.0
bind_port = %(api_port)s
registry_host = 0.0.0.0
registry_port = %(reg_port)s

[app:glance-registry]
paste.app_factory = glance.registry.server:app_factory
bind_host = 0.0.0.0
bind_port = %(reg_port)s
sql_connection = sqlite://
sql_idle_timeout = 3600
""" % locals()
            conf_file.write(conf_contents)
            conf_file.flush()
            conf_file_name = conf_file.name

            venv = ""
            if 'VIRTUAL_ENV' in os.environ:
                venv = "tools/with_venv.sh "

            # Start up the API and default registry server
            cmd = venv + "./bin/glance-control api start "\
                         "%s --pid-file=glance-api.pid" % conf_file_name
            exitcode, out, err = execute(cmd)

            self.assertEquals(0, exitcode)
            self.assertTrue("Starting glance-api with" in out)

            cmd = venv + "./bin/glance-control registry start "\
                         "%s --pid-file=glance-registry.pid" % conf_file_name
            exitcode, out, err = execute(cmd)

            self.assertEquals(0, exitcode)
            self.assertTrue("Starting glance-registry with" in out)

            time.sleep(2)  # Gotta give some time for spin up...

            cmd = "curl -g http://0.0.0.0:%d/images" % api_port

            exitcode, out, err = execute(cmd)

            self.assertEquals(0, exitcode)
            self.assertEquals('{"images": []}', out.strip())

            cmd = "curl -X POST -H 'Content-Type: application/octet-stream' "\
                  "-dinvalid http://0.0.0.0:%d/images" % api_port
            ignored, out, err = execute(cmd)

            self.assertTrue('Image type is required' in out,
                            "Could not find 'Image type is required' "
                            "in output: %s" % out)

            cmd = "./bin/glance-upload --port=%(api_port)d "\
                  "--type=invalid %(conf_file_name)s "\
                  "'my image'" % locals()

            # Normally, we would simply self.assertRaises() here, but
            # we also want to check that the Invalid image type is in
            # the exception text...
            hit_exception = False
            try:
                ignored, out, err = execute(cmd)
            except RuntimeError, e:
                hit_exception = True
                self.assertTrue('Invalid image type' in str(e),
                                "Could not find 'Invalid image type' in "
                                "result from glance-upload:\n%(e)s" % locals())
            self.assertTrue(hit_exception)

            # Spin down the API and default registry server
            cmd = "./bin/glance-control api stop "\
                  "%s --pid-file=glance-api.pid" % conf_file_name
            ignored, out, err = execute(cmd)
            cmd = "./bin/glance-control registry stop "\
                  "%s --pid-file=glance-registry.pid" % conf_file_name
            ignored, out, err = execute(cmd)
