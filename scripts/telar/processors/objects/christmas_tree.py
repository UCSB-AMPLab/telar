"""Christmas Tree Mode: objects that light up every warning path.

Version: v1.7.0
"""

import pandas as pd


def inject_christmas_tree_errors(df):
    """
    Inject test objects with various error conditions for testing multilingual warnings.
    All test objects have a Christmas tree emoji in their titles for easy identification.

    This "Christmas Tree Mode" lights up all possible warning messages.

    Args:
        df: pandas DataFrame of objects

    Returns:
        pandas DataFrame with test objects appended
    """
    test_objects = [
        {
            'object_id': 'test-iiif-404',
            'title': '\U0001f384 Test - IIIF 404 Error',
            'description': 'Test object to trigger IIIF 404 error warning',
            'iiif_manifest': 'https://example.com/nonexistent/manifest.json',
            'creator': 'Test',
            'period': 'Test',
            'source': '',
            'credit': '',
            'thumbnail': ''
        },
        {
            'object_id': 'test-iiif-503',
            'title': '\U0001f384 Test - IIIF 503 Service Unavailable',
            'description': 'Test object to trigger IIIF 503 error warning',
            'iiif_manifest': 'https://httpstat.us/503',
            'creator': 'Test',
            'period': 'Test',
            'source': '',
            'credit': '',
            'thumbnail': ''
        },
        {
            'object_id': 'test-iiif-invalid',
            'title': '\U0001f384 Test - Invalid IIIF URL',
            'description': 'Test object to trigger invalid URL warning',
            'iiif_manifest': 'not-a-valid-url',
            'creator': 'Test',
            'period': 'Test',
            'source': '',
            'credit': '',
            'thumbnail': ''
        },
        {
            'object_id': 'test-image-missing',
            'title': '\U0001f384 Test - Missing Image Source',
            'description': 'Test object with no IIIF manifest and no local image file',
            'iiif_manifest': '',
            'creator': 'Test',
            'period': 'Test',
            'source': '',
            'credit': '',
            'thumbnail': ''
        },
        {
            'object_id': 'test-iiif-500',
            'title': '\U0001f384 Test - IIIF 500 Internal Server Error',
            'description': 'Test object to trigger IIIF 500 error warning',
            'iiif_manifest': 'https://httpstat.us/500',
            'creator': 'Test',
            'period': 'Test',
            'source': '',
            'credit': '',
            'thumbnail': ''
        },
        {
            'object_id': 'test-iiif-429',
            'title': '\U0001f384 Test - IIIF 429 Rate Limiting',
            'description': 'Test object to trigger IIIF 429 rate limiting warning',
            'iiif_manifest': 'https://httpstat.us/429',
            'creator': 'Test',
            'period': 'Test',
            'source': '',
            'credit': '',
            'thumbnail': ''
        }
    ]

    # Create dataframe from test objects and concatenate with existing data
    test_df = pd.DataFrame(test_objects)
    df = pd.concat([df, test_df], ignore_index=True)

    print("\U0001f384 Christmas Tree Mode activated - injected test objects with various errors")

    return df
