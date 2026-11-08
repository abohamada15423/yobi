# -*- coding: utf-8 -*-
"""
Secure credential storage for auto-login.

Uses the `keyring` library, which on Windows maps to Credential Manager
(DPAPI-encrypted per user). Nothing is ever written to a plain JSON file.
"""

import keyring

SERVICE_NAME = "Yobi"


def save_credentials(account_key, username, password):
    """Save (username, password) for `account_key` (e.g. 'riot', 'steam').
    Returns True on success."""
    try:
        keyring.set_password(SERVICE_NAME, f"{account_key}::user", username)
        keyring.set_password(SERVICE_NAME, f"{account_key}::pass", password)
        return True
    except Exception as e:
        print(f"⚠️ keyring save failed: {e}")
        return False


def load_credentials(account_key):
    """Return (username, password) or (None, None) if not saved."""
    try:
        user = keyring.get_password(SERVICE_NAME, f"{account_key}::user")
        pwd = keyring.get_password(SERVICE_NAME, f"{account_key}::pass")
        if user and pwd:
            return user, pwd
    except Exception as e:
        print(f"⚠️ keyring load failed: {e}")
    return None, None


def has_credentials(account_key):
    user, pwd = load_credentials(account_key)
    return bool(user and pwd)


def delete_credentials(account_key):
    """Remove saved credentials for `account_key`."""
    for suffix in ("::user", "::pass"):
        try:
            keyring.delete_password(SERVICE_NAME, f"{account_key}{suffix}")
        except Exception:
            pass