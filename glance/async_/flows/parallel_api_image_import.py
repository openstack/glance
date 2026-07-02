# Copyright 2026 RedHat Inc.
# Copyright 2026 OpenStack Foundation
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

"""Parallel multi-store import for interoperable image import.

When ``max_parallel_stores`` > 1 and more than one backend is requested,
``api_image_import.get_flow`` runs this module instead of one
``_ImportToStore`` task per store. Default config keeps the serial path.

Supported import methods: glance-direct, web-download, and glance-download.
``copy-image`` is not supported and always uses the sequential per-store path.
"""

from concurrent import futures
import os
import queue
import threading

from cryptography import exceptions as crypto_exception
from cursive import exception as cursive_exception
from cursive import signature_utils
import glance_store as store_api
from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils.imageutils import format_inspector
from taskflow import task
from taskflow.types import failure as tf_failure

from glance.common import exception
from glance.common.scripts import utils as script_utils
from glance.common import store_utils
from glance.common import utils as common_utils
from glance import db as db_api
from glance.i18n import _, _LI

CONF = cfg.CONF
LOG = logging.getLogger(__name__)

_SUPPORTED_PARALLEL_IMPORT_METHODS = frozenset(
    ('glance-direct', 'web-download', 'glance-download'))

# Location metadata: marks in-progress rows owned by this import flow.
LOC_META_IMPORT_TAG = 'os_glance_parallel_import'
LOC_META_IMPORT_TAG_VALUE = 'pending'


def should_use_parallel_store_import(import_method, stores):
    """Return True when parallel store import should run.

    When False, get_flow uses the existing _ImportToStore chain.
    """
    if import_method not in _SUPPORTED_PARALLEL_IMPORT_METHODS:
        return False
    if not CONF.enabled_backends:
        return False
    if CONF.image_import_opts.max_parallel_stores <= 1:
        return False
    if not stores:
        return False
    return len(stores) > 1


def add_parallel_store_import_tasks(flow, task_id, task_type, task_repo,
                                    action_wrapper, file_uri, stores,
                                    all_stores_must_succeed, import_method,
                                    context, image_repo):
    """Add staged signature verify and parallel multi-store import tasks."""
    image_id = action_wrapper.image_id
    LOG.debug(
        'Adding parallel multi-store import tasks %(task)s for image '
        '%(image)s stores=%(stores)s all_stores_must_succeed=%(all)s',
        {'task': task_id, 'image': image_id,
         'stores': ','.join(stores), 'all': all_stores_must_succeed})
    flow.add(_VerifyStagedImageSignatureTask(
        task_id, task_type, context, image_repo, action_wrapper, file_uri,
        image_id, stores))
    flow.add(_ParallelStoreImportTask(
        task_id, task_type, task_repo, action_wrapper, file_uri, stores,
        all_stores_must_succeed, import_method, context, image_repo))


def _placeholder_location_url(image_id, store):
    """Placeholder DB url until the real store location is known.

    ``store`` is the target backend name from the import request. Parallel
    import only runs with multi-backend enabled, so it is normally always set.
    ``None`` is not expected in this flow (it is used elsewhere for the legacy
    single-store default), but is normalized to ``'_'`` so the placeholder URL
    stays unique if it ever appears.
    """
    return 'pending://parallel-import/%s/%s' % (image_id, store or '_')


def _location_metadata(loc):
    """Return location metadata dict from db.image_get() location entry."""
    meta = loc.get('metadata')
    return meta if isinstance(meta, dict) else {}


def _is_in_progress_import_location(loc):
    """True for our pending/uploading rows (not normal active locations)."""
    status = loc.get('status')
    if status not in ('pending', 'uploading'):
        return False
    meta = _location_metadata(loc)
    return meta.get(LOC_META_IMPORT_TAG) == LOC_META_IMPORT_TAG_VALUE


def _create_upload_verifier(context, extra_properties):
    """Build a signature verifier when image signature properties are set."""
    if not signature_utils.should_create_verifier(extra_properties):
        return None
    return signature_utils.get_verifier(
        context=context,
        img_signature_certificate_uuid=extra_properties[
            signature_utils.CERT_UUID],
        img_signature_hash_method=extra_properties[
            signature_utils.HASH_METHOD],
        img_signature=extra_properties[signature_utils.SIGNATURE],
        img_signature_key_type=extra_properties[signature_utils.KEY_TYPE])


def _delete_staged_import_file(file_path):
    """Remove staged image data"""
    if CONF.enabled_backends:
        try:
            store_api.delete(file_path, 'os_glance_staging_store')
        except store_api.exceptions.NotFound:
            LOG.warning(
                'Staged image data not found at %(path)s during cleanup',
                {'path': file_path})
    else:
        path = file_path[7:] if file_path.startswith('file://') else file_path
        if os.path.exists(path):
            try:
                os.unlink(path)
            except OSError as exc:
                LOG.warning(
                    'Failed to delete staged image data at %(path)s: %(err)s',
                    {'path': path, 'err': exc})


def _verify_staged_image_signature(context, extra_properties, staged_uri,
                                   image_id):
    """Verify image signature once against staged data before store copies."""
    verifier = _create_upload_verifier(context, extra_properties)
    if verifier is None:
        return

    data_iter, _size = script_utils.get_image_data_iter(staged_uri)
    try:
        for chunk in data_iter:
            if chunk:
                verifier.update(chunk)
        verifier.verify()
        LOG.info(_LI('Successfully verified signature for image %s'),
                 image_id)
    except crypto_exception.InvalidSignature:
        raise cursive_exception.SignatureVerificationError(
            _('Signature verification failed'))
    finally:
        if hasattr(data_iter, 'close'):
            data_iter.close()


def _verify_uploaded_attribute(image, value, attribute_name):
    """Reject upload when staged data disagrees with image metadata."""
    image_value = getattr(image, attribute_name, None)
    if image_value is not None and value != image_value:
        msg = _("%s of uploaded data is different from current "
                "value set on the image.")
        LOG.error(msg, attribute_name)
        raise exception.UploadException(msg % attribute_name)


def _prepare_upload_data(data_iter, container_format, disk_format):
    """Apply in-flight format inspection for bare images (see set_data)."""
    if container_format == 'bare':
        LOG.debug('Enabling in-flight format inspection for %s', disk_format)
        return format_inspector.InspectWrapper(data_iter)
    return data_iter


def _import_staged_data_to_store(context, image, staged_uri, store,
                                 hash_algo, task_repo, task_id, cancel_event):
    """Read staged file and write one copy to a single backend."""
    image_id = image.image_id
    LOG.debug(
        'Parallel import copying staged data to store %(store)s for image '
        '%(image)s',
        {'store': store, 'image': image_id})
    data_iter, size = script_utils.get_image_data_iter(staged_uri)
    upload_data = None
    try:
        if image.size is not None and image.size != size:
            msg = _(
                "Task %(task_id)s: Image size mismatch. Expected %(expected)d "
                "but got %(actual)d") % {
                    'task_id': task_id,
                    'expected': image.size,
                    'actual': size}
            raise exception.ImportTaskError(msg)

        upload_data = _prepare_upload_data(
            data_iter, image.container_format, image.disk_format)

        def _check_task_still_running(chunk_bytes, total_bytes):
            if cancel_event.is_set():
                LOG.debug(
                    'Aborting import to store %(store)s for image %(image)s',
                    {'store': store, 'image': image_id})
                raise exception.TaskAbortedError()
            task = script_utils.get_task(task_repo, task_id)
            if task is None:
                raise exception.TaskNotFound(task_id)
            if task.status != 'processing':
                raise exception.TaskAbortedError()

        try:
            data = script_utils.CallbackIterator(
                common_utils.wrap_data_for_store_upload(upload_data),
                _check_task_still_running, min_interval=60)
            (location, bytes_written, checksum, os_hash,
             store_meta) = store_api.add_with_multihash(
                CONF, image_id, data, size, store, hash_algo,
                context=context)
        except format_inspector.ImageFormatError as exc:
            raise exception.InvalidImageData(str(exc))

        locs = [{'url': location, 'metadata': store_meta or {}}]
        locs = store_utils.get_updated_store_location(locs, context=context)
        loc = locs[0]
        _verify_uploaded_attribute(image, bytes_written, 'size')
        _verify_uploaded_attribute(image, checksum, 'checksum')
        _verify_uploaded_attribute(image, os_hash, 'os_hash_value')
        LOG.debug(
            'Parallel import finished store %(store)s for image %(image)s '
            'size=%(size)s',
            {'store': store, 'image': image_id, 'size': bytes_written})
        return {
            'store': store,
            'url': loc['url'],
            'metadata': loc['metadata'],
            'size': bytes_written,
            'checksum': checksum,
            'os_hash_value': os_hash,
        }
    finally:
        stream_to_close = upload_data if upload_data is not None else data_iter
        if hasattr(stream_to_close, 'close'):
            stream_to_close.close()


class _VerifyStagedImageSignatureTask(task.Task):
    """Verify signed image once on staging before parallel store copies."""

    def __init__(self, task_id, task_type, context, image_repo,
                 action_wrapper, file_uri, image_id, stores):
        self.task_id = task_id
        self.task_type = task_type
        self.context = context
        self.image_repo = image_repo
        self.action_wrapper = action_wrapper
        self.file_uri = file_uri
        self.image_id = image_id
        self.stores = list(stores)
        super(_VerifyStagedImageSignatureTask, self).__init__(
            name='%s-VerifyStagedSignature-%s' % (task_type, task_id))

    def execute(self, file_path=None):
        image = self.image_repo.get(self.image_id)
        _verify_staged_image_signature(
            self.context, image.extra_properties,
            file_path or self.file_uri, self.image_id)

    def revert(self, result, file_path=None, **kwargs):
        """On signature failure, reset image state and drop staged data."""
        if not isinstance(result, tf_failure.Failure):
            return

        LOG.warning(
            'Parallel import signature verification failed for image '
            '%(image)s; reverting to queued',
            {'image': self.image_id})
        with self.action_wrapper as action:
            action.set_image_attribute(status='queued')
            action.remove_importing_stores(self.stores)
            action.add_failed_stores(self.stores)

        staged_path = file_path or self.file_uri
        if staged_path:
            _delete_staged_import_file(staged_path)


class _ParallelStoreImportTask(task.Task):
    """Import staged image to multiple stores (bounded worker pool)."""

    def __init__(self, task_id, task_type, task_repo, action_wrapper, file_uri,
                 stores, all_stores_must_succeed, import_method, context,
                 image_repo):
        self.task_id = task_id
        self.task_type = task_type
        self.task_repo = task_repo
        self.action_wrapper = action_wrapper
        self.file_uri = file_uri
        self.stores = list(stores)
        self.all_stores_must_succeed = all_stores_must_succeed
        self.import_method = import_method
        self.context = context
        self.image_repo = image_repo
        self._completed_imports = []
        self._import_location_row_ids = []
        super(_ParallelStoreImportTask, self).__init__(
            name='%s-ParallelStoreImport-%s' % (task_type, task_id))

    def _create_pending_location_rows(self, db, image_id):
        """Insert pending rows; return store_name -> location_row_id."""
        location_id_by_store = {}
        for store in self.stores:
            url = _placeholder_location_url(image_id, store)
            meta = {
                'store': store,
                LOC_META_IMPORT_TAG: LOC_META_IMPORT_TAG_VALUE,
            }
            common_utils.retry_on_db_lock(
                lambda store=store, url=url, meta=meta: db.image_location_add(
                    self.context, image_id,
                    {'url': url, 'metadata': meta, 'status': 'pending'}))
        # NOTE(abhishekk): image_location_add() does not return the new row id,
        # but workers must update the same row (pending -> uploading -> active)
        # via image_location_update(), which requires id. Reload locations and
        # map each target store to its pending row for parallel workers.
        image_from_db = common_utils.retry_on_db_lock(
            lambda: db.image_get(self.context, image_id))
        for loc in image_from_db['locations']:
            if not _is_in_progress_import_location(loc):
                continue
            meta = _location_metadata(loc)
            store_name = meta.get('store')
            if store_name in self.stores:
                location_id_by_store[store_name] = loc['id']
                self._import_location_row_ids.append(loc['id'])
        LOG.debug(
            'Registered pending location rows for image %(image)s: '
            '%(mapping)s',
            {'image': image_id,
             'mapping': ','.join('%s=%s' % (s, i) for s, i in
                                 sorted(location_id_by_store.items()))})
        return location_id_by_store

    def _update_location_row(self, db, image_id, row_id, url, meta, status):
        LOG.debug(
            'Parallel import location %(row)s image %(image)s -> %(status)s',
            {'row': row_id, 'image': image_id, 'status': status})
        common_utils.retry_on_db_lock(
            lambda: db.image_location_update(
                self.context, image_id,
                {'id': row_id, 'url': url, 'metadata': meta,
                 'status': status}))

    def _delete_location_rows(self, db, image_id, row_ids):
        for row_id in row_ids:
            try:
                common_utils.retry_on_db_lock(
                    lambda row_id=row_id: db.image_location_delete(
                        self.context, image_id, row_id, 'deleted'))
            except Exception:
                LOG.warning(
                    'Could not delete parallel-import location %(row)s for '
                    'image %(image)s',
                    {'row': row_id, 'image': image_id}, exc_info=True)

    def _sync_locations_from_db(self, db, image_id, action):
        """Merge DB location rows onto the image before repo.save."""
        # NOTE(abhishekk): Parallel workers update per-store location rows
        # directly via image_location_* (pending -> uploading -> active). When
        # ImportActionWrapper reloads the image for the final save, the domain
        # object may still carry placeholder URLs from an earlier load. Update
        # each known row in place by id and append any new rows from the DB
        # rather than replacing action._image.locations wholesale. Assigning a
        # new list with changed URLs triggers StoreLocations validation
        # ("Original locations is not empty") under native-threaded workers.
        image_from_db = common_utils.retry_on_db_lock(
            lambda: db.image_get(self.context, image_id))
        db_loc = {
            loc['id']: loc for loc in image_from_db['locations']
            if loc.get('id')}

        known_ids = set()
        for loc in action._image.locations:
            row_id = loc.get('id')
            if row_id and row_id in db_loc:
                loc['url'] = db_loc[row_id]['url']
                loc['metadata'] = _location_metadata(db_loc[row_id])
                loc['status'] = db_loc[row_id].get('status', 'active')
                known_ids.add(row_id)

        for row_id in db_loc:
            if row_id not in known_ids:
                action._image.locations.append({
                    'id': row_id,
                    'url': db_loc[row_id]['url'],
                    'metadata': _location_metadata(db_loc[row_id]),
                    'status': db_loc[row_id].get('status', 'active'),
                })

    def _delete_uploaded_backend_data(self, import_result):
        location = {
            'url': import_result['url'],
            'metadata': import_result['metadata'],
        }
        image_id = self.action_wrapper.image_id
        LOG.debug(
            'Deleting backend object for store %(store)s image %(image)s',
            {'store': import_result.get('store'), 'image': image_id})
        try:
            store_utils.delete_image_location_from_backend(
                self.context, image_id, location)
        except Exception:
            LOG.exception(
                'Failed to delete backend object for store %(store)s image '
                '%(image)s',
                {'store': import_result.get('store'), 'image': image_id})

    def _activate_image_on_first_store(self, db, image_id, import_result,
                                       hash_algo, activate_lock,
                                       image_activated):
        """When any store may succeed, set image active after the first one.

        Per-store location rows are updated via direct DB calls during
        parallel workers. Reconcile image locations in execute().
        """
        with activate_lock:
            if image_activated[0]:
                return
            LOG.info(_LI(
                'Parallel import setting image %(image)s active after first '
                'successful store %(store)s'),
                {'image': image_id, 'store': import_result['store']})
            common_utils.retry_on_db_lock(
                lambda: db.image_update(
                    self.context, image_id, {
                        'status': 'active',
                        'size': import_result['size'],
                        'checksum': import_result['checksum'],
                        'os_hash_value': import_result['os_hash_value'],
                        'os_hash_algo': hash_algo,
                    }, from_state='importing'))
            image_activated[0] = True

    def _import_to_one_store(self, store, location_id_by_store, db, image,
                             staged_uri, hash_algo, cancel_event,
                             successful_imports, failed_stores, imports_lock,
                             activate_lock, image_activated):
        image_id = image.image_id
        row_id = location_id_by_store.get(store)
        placeholder_url = _placeholder_location_url(image_id, store)
        row_meta = {
            'store': store,
            LOC_META_IMPORT_TAG: LOC_META_IMPORT_TAG_VALUE,
        }
        LOG.debug(
            'Parallel import worker starting store %(store)s for image '
            '%(image)s location_row_id=%(row)s',
            {'store': store, 'image': image_id, 'row': row_id})
        if row_id is not None:
            self._update_location_row(
                db, image_id, row_id, placeholder_url, row_meta, 'uploading')
        try:
            import_result = _import_staged_data_to_store(
                self.context, image, staged_uri, store, hash_algo,
                self.task_repo, self.task_id, cancel_event)
            if cancel_event.is_set():
                LOG.warning(
                    'Discarding completed upload to store %(store)s for image '
                    '%(image)s because parallel import was aborted',
                    {'store': store, 'image': image_id})
                self._delete_uploaded_backend_data(import_result)
                return
            if row_id is not None:
                self._update_location_row(
                    db, image_id, row_id, import_result['url'],
                    import_result['metadata'], 'active')
            else:
                common_utils.retry_on_db_lock(
                    lambda: db.image_location_add(
                        self.context, image_id,
                        {'url': import_result['url'],
                         'metadata': import_result['metadata'],
                         'status': 'active'}))
            with imports_lock:
                successful_imports.append(import_result)
            if not self.all_stores_must_succeed:
                self._activate_image_on_first_store(
                    db, image_id, import_result, hash_algo, activate_lock,
                    image_activated)
        except Exception as exc:
            with imports_lock:
                failed_stores[store] = exc
            LOG.warning(
                'Parallel import store %(store)s failed for image '
                '%(image)s: %(err)s',
                {'store': store, 'image': image_id, 'err': exc})
            if row_id is not None:
                try:
                    self._delete_location_rows(db, image_id, [row_id])
                except Exception:
                    pass
            if self.all_stores_must_succeed:
                LOG.warning(
                    'Parallel import aborting remaining stores for image '
                    '%(image)s after store %(store)s failed',
                    {'image': image_id, 'store': store})
                cancel_event.set()
                with imports_lock:
                    for import_result in list(successful_imports):
                        self._delete_uploaded_backend_data(import_result)
                    successful_imports.clear()

    def _store_worker(self, store_queue, location_id_by_store, db, image,
                      staged_uri, hash_algo, cancel_event, successful_imports,
                      failed_stores, imports_lock, activate_lock,
                      image_activated):
        while not cancel_event.is_set():
            try:
                store = store_queue.get_nowait()
            except queue.Empty:
                return
            try:
                self._import_to_one_store(
                    store, location_id_by_store, db, image, staged_uri,
                    hash_algo, cancel_event, successful_imports,
                    failed_stores, imports_lock, activate_lock,
                    image_activated)
            finally:
                store_queue.task_done()

    def execute(self, file_path=None):
        staged_uri = file_path or self.file_uri
        image_id = self.action_wrapper.image_id
        num_workers = min(CONF.image_import_opts.max_parallel_stores,
                          len(self.stores))

        image = self.image_repo.get(image_id)
        hash_algo = image.os_hash_algo or CONF['hashing_algorithm']

        LOG.info(_LI(
            'Parallel store import starting for image %(image)s: '
            'stores=%(stores)s num_workers=%(workers)s '
            'all_stores_must_succeed=%(all)s method=%(method)s'),
            {'image': image_id, 'stores': ','.join(self.stores),
             'workers': num_workers, 'all': self.all_stores_must_succeed,
             'method': self.import_method})

        db = db_api.get_api()
        self._import_location_row_ids = []
        location_id_by_store = self._create_pending_location_rows(db, image_id)

        store_queue = queue.Queue()
        for store in self.stores:
            store_queue.put(store)

        cancel_event = threading.Event()
        successful_imports = []
        failed_stores = {}
        imports_lock = threading.Lock()
        activate_lock = threading.Lock()
        # NOTE(abhishekk): One-element list so worker threads can set
        # image_activated[0] = True in place; a plain bool would not be
        # shared across the thread pool and execute().
        image_activated = [False]

        with futures.ThreadPoolExecutor(max_workers=num_workers) as pool:
            worker_threads = [
                pool.submit(
                    self._store_worker, store_queue, location_id_by_store,
                    db, image, staged_uri, hash_algo, cancel_event,
                    successful_imports, failed_stores, imports_lock,
                    activate_lock, image_activated)
                for _ in range(num_workers)
            ]
            for thread in futures.as_completed(worker_threads):
                thread.result()

        if self.all_stores_must_succeed and failed_stores:
            first_error = next(iter(failed_stores.values()))
            LOG.error(
                'Parallel import failed for image %(image)s: %(failed)s '
                'succeeded=%(ok)s error=%(err)s',
                {'image': image_id,
                 'failed': ','.join(sorted(failed_stores)),
                 'ok': ','.join(i['store'] for i in successful_imports),
                 'err': first_error})
            for import_result in list(successful_imports):
                self._delete_uploaded_backend_data(import_result)
            successful_imports.clear()
            self._delete_location_rows(
                db, image_id, self._import_location_row_ids)
            self._import_location_row_ids = []
            raise exception.ImportTaskError(
                _('Parallel import failed for image %(image)s: %(err)s') % {
                    'image': image_id, 'err': first_error})

        if not successful_imports:
            LOG.error(
                'Parallel import: no store succeeded for image %(image)s '
                'errors=%(errors)s',
                {'image': image_id,
                 'errors': ','.join(
                     '%s:%s' % (s, e) for s, e in
                     sorted(failed_stores.items()))})
            self._delete_location_rows(
                db, image_id, self._import_location_row_ids)
            raise exception.ImportTaskError(
                _('No store import succeeded for image %s') % image_id)

        first_import_result = successful_imports[0]
        self._completed_imports = list(successful_imports)

        with self.action_wrapper as action:
            action.remove_importing_stores(self.stores)
            for store in failed_stores:
                action.add_failed_stores([store])
            if self.all_stores_must_succeed or not image_activated[0]:
                action.set_image_attribute(
                    status='active', size=first_import_result['size'])
                image = action._image
                image.checksum = first_import_result['checksum']
                image.os_hash_value = first_import_result['os_hash_value']
                image.os_hash_algo = hash_algo
            self._sync_locations_from_db(db, image_id, action)

        LOG.info(_LI(
            'Parallel store import finished for image %(image)s: '
            'succeeded=%(ok)s failed=%(failed)s'),
            {'image': image_id,
             'ok': ','.join(i['store'] for i in successful_imports),
             'failed': ','.join(sorted(failed_stores)) or '(none)'})

        self._import_location_row_ids = []

    def revert(self, result, **kwargs):
        completed = getattr(self, '_completed_imports', [])
        if completed:
            LOG.warning(
                'Reverting parallel store import for image %(image)s, '
                'deleting %(count)s backend object(s)',
                {'image': self.action_wrapper.image_id,
                 'count': len(completed)})
        for import_result in completed:
            self._delete_uploaded_backend_data(import_result)
