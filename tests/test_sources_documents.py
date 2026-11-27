"""scripts.download_sources checks Documents 4-10 by SHA-256 (docs/sources.md)."""
import hashlib

from scripts import download_sources as ds
from src.documents import config


def test_documents_are_reported_same_different_or_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RAW_DIR", tmp_path)
    monkeypatch.setattr(ds, "DOCUMENT_URLS", {})          # never touch the network in tests
    real = b"group copy"
    doc4, doc5 = config.BY_ID[4], config.BY_ID[5]
    monkeypatch.setattr(config, "DOCUMENTS", (
        config.Document(**{**doc4.__dict__, "sha256": hashlib.sha256(real).hexdigest()}),
        doc5, config.BY_ID[6]))
    (tmp_path / doc4.file).write_bytes(real)
    (tmp_path / doc5.file).write_bytes(b"another version")
    status = ds.ensure_documents(verbose=False)
    assert status == {4: "same", 5: "different", 6: "missing"}


def test_every_document_has_a_listing_page_and_a_fingerprint():
    for d in config.DOCUMENTS:
        assert ds._document_page(d.id).startswith("https://")
        assert len(d.sha256) == 64
