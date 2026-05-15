"""
TimeScreen Control - Security Functions
Password hashing with bcrypt for maximum security.
"""

import hashlib
import json
from typing import Optional

try:
    import bcrypt
    BCRYPT_AVAILABLE = True
except ImportError:
    BCRYPT_AVAILABLE = False


def hash_password(password: str) -> str:
    """
    Hash password using bcrypt (preferred) or SHA-256 fallback.
    
    Args:
        password: Plain text password
        
    Returns:
        Hashed password string
    """
    if BCRYPT_AVAILABLE:
        salt = bcrypt.gensalt(rounds=12)
        return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')
    else:
        # Fallback to SHA-256 with salt (less secure but works without dependencies)
        import secrets
        salt = secrets.token_hex(16)
        salted = salt + password
        hash_obj = hashlib.sha256(salted.encode('utf-8'))
        return f"$sha256${salt}${hash_obj.hexdigest()}"


def verify_password(password: str, hashed: str) -> bool:
    """
    Verify password against stored hash.
    
    Args:
        password: Plain text password to verify
        hashed: Stored hash
        
    Returns:
        True if password matches, False otherwise
    """
    if not hashed:
        return False
    
    # Check if it's a bcrypt hash (starts with $2b$ or $2a$)
    if hashed.startswith('$2b$') or hashed.startswith('$2a$'):
        if BCRYPT_AVAILABLE:
            try:
                return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
            except Exception:
                return False
        else:
            raise RuntimeError("bcrypt required to verify bcrypt hashes")
    
    # Check if it's our SHA-256 format: $sha256$salt$hash
    if hashed.startswith('$sha256$'):
        parts = hashed.split('$')
        if len(parts) != 4:
            return False
        salt = parts[2]
        stored_hash = parts[3]
        salted = salt + password
        computed = hashlib.sha256(salted.encode('utf-8')).hexdigest()
        return computed == stored_hash
    
    # Legacy format: plain SHA-256 without salt (insecure, force reset)
    if len(hashed) == 64 and all(c in '0123456789abcdef' for c in hashed):
        return False  # Force password reset for legacy hashes
    
    return False


def compute_hash(data: dict) -> str:
    """
    Compute integrity hash for configuration data.
    
    Args:
        data: Configuration dictionary (without _hash field)
        
    Returns:
        Short hash string for integrity verification
    """
    clean = {k: v for k, v in data.items() if k != "_hash"}
    payload = json.dumps(clean, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]
