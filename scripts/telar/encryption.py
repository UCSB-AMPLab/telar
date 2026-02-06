"""
Story Encryption Module

This module provides client-side encryption for protected stories using
AES-GCM. Protected stories are encrypted at build time; the browser
decrypts them at runtime using the Web Crypto API.

The encryption uses:
- PBKDF2 with 100,000 iterations for key derivation
- AES-256-GCM for authenticated encryption
- Random salt (16 bytes) and IV (12 bytes) per story

The encrypted format stores salt and IV alongside the ciphertext so the
browser can derive the same key and decrypt the content.

Version: v0.8.0-beta
"""

import base64
import json
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes


# PBKDF2 iterations — must match the JavaScript decryption code
PBKDF2_ITERATIONS = 100000


def derive_key(password: str, salt: bytes) -> bytes:
    """
    Derive a 256-bit encryption key from password and salt using PBKDF2.

    Args:
        password: User-provided story key
        salt: Random 16-byte salt

    Returns:
        32-byte derived key for AES-256
    """
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=PBKDF2_ITERATIONS,
    )
    return kdf.derive(password.encode('utf-8'))


def encrypt_story(story_data: list, story_key: str) -> dict:
    """
    Encrypt story JSON data using AES-GCM.

    Args:
        story_data: List of story steps (the full story JSON)
        story_key: User-provided encryption key from _config.yml

    Returns:
        dict with encrypted format:
        {
            "encrypted": True,
            "salt": base64-encoded salt,
            "iv": base64-encoded IV,
            "ciphertext": base64-encoded encrypted data
        }
    """
    # Generate random salt and IV
    salt = os.urandom(16)
    iv = os.urandom(12)  # 96 bits for AES-GCM

    # Derive encryption key from user's key
    key = derive_key(story_key, salt)

    # Encrypt story data
    aesgcm = AESGCM(key)
    plaintext = json.dumps(story_data, ensure_ascii=False).encode('utf-8')
    ciphertext = aesgcm.encrypt(iv, plaintext, None)

    # Return encrypted format
    return {
        'encrypted': True,
        'salt': base64.b64encode(salt).decode('ascii'),
        'iv': base64.b64encode(iv).decode('ascii'),
        'ciphertext': base64.b64encode(ciphertext).decode('ascii')
    }


def get_protected_stories(project_data: list) -> set:
    """
    Extract set of protected story identifiers from project.json data.

    Args:
        project_data: List containing project data (with 'stories' key)

    Returns:
        Set of story identifiers (story_id or story number) that are protected
    """
    protected = set()

    for item in project_data:
        if 'stories' in item:
            for story in item['stories']:
                if story.get('protected'):
                    # Use story_id if available, otherwise use number
                    story_id = story.get('story_id') or story.get('number')
                    if story_id:
                        protected.add(str(story_id))

    return protected


def get_story_key_from_config(config: dict) -> str:
    """
    Extract story_key from _config.yml data.

    Args:
        config: Parsed _config.yml dictionary

    Returns:
        Story key string, or empty string if not configured
    """
    return config.get('story_key', '')
