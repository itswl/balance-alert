from database.engine import _mask_database_url


def test_mask_database_url_hides_password():
    url = 'postgresql://admin:secret-pass@example.com:5432/balance'

    masked = _mask_database_url(url)

    assert 'secret-pass' not in masked
    assert masked == 'postgresql://admin:***@example.com:5432/balance'


def test_mask_database_url_leaves_sqlite_url_readable():
    url = 'sqlite:///./data/balance_alert.db'

    assert _mask_database_url(url) == url
