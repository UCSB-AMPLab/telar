"""Choosing which objects the homepage samples.

Version: v1.7.0
"""

import hashlib
import random
from pathlib import Path

import yaml


def _select_featured_objects(df):
    """
    Select objects to feature on the homepage.

    If any objects have featured=yes, those are selected.
    Otherwise, randomly select objects (count from config, default 4).
    Selected objects are marked with is_featured_sample=true.

    Args:
        df: pandas DataFrame of objects

    Returns:
        pandas DataFrame with is_featured_sample column added
    """
    # Read config for settings
    config = {}
    config_path = Path('_config.yml')
    if config_path.exists():
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f) or {}
        except Exception as e:
            print(f"  [WARN] Could not read _config.yml for featured objects: {e}")

    # Get settings from collection_interface
    collection_config = config.get('collection_interface', {})
    show_sample = collection_config.get('show_sample_on_homepage', False)
    featured_count = collection_config.get('featured_count', 4)

    # Initialize column
    df['is_featured_sample'] = False

    # Skip if show_sample_on_homepage is disabled
    if not show_sample:
        return df

    # Check for explicitly featured objects (case-insensitive yes/true/si)
    featured_values = {'yes', 'true', 'si', 'sí', '1'}
    if 'featured' in df.columns:
        featured_mask = df['featured'].astype(str).str.lower().str.strip().isin(featured_values)
        featured_objects = df[featured_mask]

        if len(featured_objects) > 0:
            # Use explicitly featured objects
            df.loc[featured_mask, 'is_featured_sample'] = True
            print(f"  [INFO] Selected {len(featured_objects)} explicitly featured object(s) for homepage")
            return df

    # No explicit featured objects — select randomly
    # Filter to objects without warnings (only show good objects on homepage)
    valid_objects = df[df['object_warning'].astype(str).str.strip() == '']

    if len(valid_objects) == 0:
        print("  [INFO] No valid objects available for homepage sample")
        return df

    # Select up to featured_count objects. Seed a local RNG from the sorted
    # object IDs so the homepage sample is reproducible across builds of
    # unchanged content (authors who want a fixed set use the `featured` flag).
    # Use a stable hash (sha256) rather than the built-in hash(), which is
    # salted per-process (PYTHONHASHSEED) and would not be reproducible.
    sample_size = min(featured_count, len(valid_objects))
    seed_key = '\n'.join(sorted(str(i) for i in valid_objects.index)).encode('utf-8')
    seed = int.from_bytes(hashlib.sha256(seed_key).digest()[:8], 'big')
    rng = random.Random(seed)
    sample_indices = rng.sample(list(valid_objects.index), sample_size)

    df.loc[sample_indices, 'is_featured_sample'] = True
    print(f"  [INFO] Randomly selected {sample_size} object(s) for homepage sample")

    return df
