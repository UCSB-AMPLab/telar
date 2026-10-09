"""Unit Tests for Judging a IIIF Manifest by What It Contains

A manifest is valid when its body is JSON with `@context` or a type, whatever
the server says it is. Object stores serve files with the content type they
were uploaded with, and a manifest uploaded without one comes back as
`application/octet-stream`: the viewer loads it, so the object page must not
tell the author that it is not a manifest, and the metadata the build reads
from it must still be read. A body that is not JSON is still reported.

Version: v1.8.1
"""

import json
import os
import sys
from unittest import mock

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from telar.processors.objects import remote

URL = 'https://s3.us-east-1.amazonaws.com/iiif-manifest-cache-production/pid-tsb-110310'

MANIFEST_V2 = {
    '@context': 'http://iiif.io/api/presentation/2/context.json',
    '@id': URL,
    '@type': 'sc:Manifest',
    'label': 'Mola panel',
    'sequences': [],
}


class _Response:
    def __init__(self, body, content_type):
        self._body = body.encode('utf-8')
        self.headers = {'Content-Type': content_type}

    def read(self, *args):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _validate(body, content_type):
    df = pd.DataFrame([{'object_id': 'kuna-0001', 'source_url': URL,
                        'title': '', 'object_warning': ''}])
    warnings = []
    with mock.patch.object(remote.urllib.request, 'urlopen',
                           return_value=_Response(body, content_type)):
        df = remote._validate_source_urls(df, {}, warnings)
    return df.iloc[0], warnings


class TestAManifestServedAsBinary:
    def test_carries_no_warning(self):
        row, _ = _validate(json.dumps(MANIFEST_V2), 'application/octet-stream')
        assert not row['object_warning']

    def test_still_gives_its_title(self):
        row, _ = _validate(json.dumps(MANIFEST_V2), 'application/octet-stream')
        assert row['title'] == 'Mola panel'


class TestAManifestServedAsJson:
    def test_carries_no_warning(self):
        row, _ = _validate(json.dumps(MANIFEST_V2), 'application/json')
        assert not row['object_warning']


class TestAPageThatIsNotJson:
    def test_is_reported_as_not_a_manifest(self):
        row, warnings = _validate('<html><body>Not found</body></html>',
                                  'text/html; charset=utf-8')
        assert row['object_warning']
        assert any('kuna-0001' in w for w in warnings)
