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

"""
Tests a Glance API server which uses the caching middleware that
uses the default SQLite cache driver. We use the filesystem store,
but that is really not relevant, as the image cache is transparent
to the backend store.
"""

import hashlib
import json
import os
import shutil
import time

import httplib2

from glance.tests import functional
from glance.tests.utils import skip_if_disabled


FIVE_KB = 5 * 1024


class BaseCacheMiddlewareTest(object):

    @skip_if_disabled
    def test_cache_middleware_transparent(self):
        """
        We test that putting the cache middleware into the
        application pipeline gives us transparent image caching
        """
        self.cleanup()
        self.start_servers(**self.__dict__.copy())

        api_port = self.api_port
        registry_port = self.registry_port

        # Add an image and verify a 200 OK is returned
        image_data = "*" * FIVE_KB
        headers = {'Content-Type': 'application/octet-stream',
                   'X-Image-Meta-Name': 'Image1',
                   'X-Image-Meta-Is-Public': 'True'}
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'POST', headers=headers,
                                         body=image_data)
        self.assertEqual(response.status, 201)
        data = json.loads(content)
        self.assertEqual(data['image']['checksum'],
                         hashlib.md5(image_data).hexdigest())
        self.assertEqual(data['image']['size'], FIVE_KB)
        self.assertEqual(data['image']['name'], "Image1")
        self.assertEqual(data['image']['is_public'], True)

        image_id = data['image']['id']

        # Verify image not in cache
        image_cached_path = os.path.join(self.api_server.image_cache_dir,
                                         image_id)
        self.assertFalse(os.path.exists(image_cached_path))

        # Grab the image
        path = "http://%s:%d/v1/images/%s" % ("0.0.0.0", self.api_port,
                                              image_id)
        http = httplib2.Http()
        response, content = http.request(path, 'GET')
        self.assertEqual(response.status, 200)

        # Verify image now in cache
        image_cached_path = os.path.join(self.api_server.image_cache_dir,
                                         image_id)

        # You might wonder why the heck this is here... well, it's here
        # because it took me forever to figure out that the disk write
        # cache in Linux was causing random failures of the os.path.exists
        # assert directly below this. Basically, since the cache is writing
        # the image file to disk in a different process, the write buffers
        # don't flush the cache file during an os.rename() properly, resulting
        # in a false negative on the file existence check below. This little
        # loop pauses the execution of this process for no more than 1.5
        # seconds. If after that time the cached image file still doesn't
        # appear on disk, something really is wrong, and the assert should
        # trigger...
        i = 0
        while not os.path.exists(image_cached_path) and i < 30:
            time.sleep(0.05)
            i = i + 1

        self.assertTrue(os.path.exists(image_cached_path))

        self.stop_servers()


class TestImageCacheXattr(functional.FunctionalTest,
                          BaseCacheMiddlewareTest):

    """Functional tests that exercise the image cache using the xattr driver"""

    def setUp(self):
        """
        Test to see if the pre-requisites for the image cache
        are working (python-xattr installed and xattr support on the
        filesystem)
        """
        if getattr(self, 'disabled', False):
            return

        if not getattr(self, 'inited', False):
            try:
                import xattr
            except ImportError:
                self.inited = True
                self.disabled = True
                self.disabled_message = ("python-xattr not installed.")
                return

        self.inited = True
        self.disabled = False
        self.cache_pipeline = "cache"
        self.image_cache_driver = "xattr"

        super(TestImageCacheXattr, self).setUp()

    def tearDown(self):
        if os.path.exists(self.api_server.image_cache_dir):
            shutil.rmtree(self.api_server.image_cache_dir)


class TestImageCacheSqlite(functional.FunctionalTest,
                           BaseCacheMiddlewareTest):

    """
    Functional tests that exercise the image cache using the
    SQLite driver
    """

    def setUp(self):
        """
        Test to see if the pre-requisites for the image cache
        are working (python-xattr installed and xattr support on the
        filesystem)
        """
        if getattr(self, 'disabled', False):
            return

        if not getattr(self, 'inited', False):
            try:
                import sqlite3
            except ImportError:
                self.inited = True
                self.disabled = True
                self.disabled_message = ("python-sqlite3 not installed.")
                return

        self.inited = True
        self.disabled = False
        self.cache_pipeline = "cache"

        super(TestImageCacheSqlite, self).setUp()

    def tearDown(self):
        if os.path.exists(self.api_server.image_cache_dir):
            shutil.rmtree(self.api_server.image_cache_dir)