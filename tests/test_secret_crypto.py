import pytest

from core.secret_crypto import decrypt_secret, encrypt_secret, encryption_enabled, is_encrypted


def test_encryption_disabled_keeps_plaintext(monkeypatch):
    monkeypatch.delenv('CONFIG_ENCRYPTION_KEY', raising=False)
    monkeypatch.delenv('BALANCE_ALERT_ENCRYPTION_KEY', raising=False)

    assert encryption_enabled() is False
    assert encrypt_secret('plain-secret') == 'plain-secret'
    assert decrypt_secret('plain-secret') == 'plain-secret'


def test_encrypt_and_decrypt_with_passphrase(monkeypatch):
    monkeypatch.setenv('CONFIG_ENCRYPTION_KEY', 'local-test-passphrase')

    encrypted = encrypt_secret('sk-test-secret')

    assert is_encrypted(encrypted)
    assert encrypted != 'sk-test-secret'
    assert decrypt_secret(encrypted) == 'sk-test-secret'


def test_encrypt_is_idempotent(monkeypatch):
    monkeypatch.setenv('CONFIG_ENCRYPTION_KEY', 'local-test-passphrase')

    encrypted = encrypt_secret('mail-password')

    assert encrypt_secret(encrypted) == encrypted


def test_fernet_key_is_supported(monkeypatch):
    pytest.importorskip('cryptography')
    from cryptography.fernet import Fernet

    monkeypatch.setenv('CONFIG_ENCRYPTION_KEY', Fernet.generate_key().decode())

    encrypted = encrypt_secret('secret-from-fernet-key')

    assert decrypt_secret(encrypted) == 'secret-from-fernet-key'
