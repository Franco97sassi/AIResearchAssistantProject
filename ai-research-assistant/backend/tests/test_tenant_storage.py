from app import tenant_storage


def test_delete_tenant_uploads_keeps_other_tenant_files(tmp_path, monkeypatch):
    monkeypatch.setattr(tenant_storage, "UPLOAD_DIR", tmp_path)
    (tmp_path / "a.pdf").write_bytes(b"a")
    (tmp_path / "b.pdf").write_bytes(b"b")
    tenant_storage.register_tenant_upload("tenant-a", "a.pdf")
    tenant_storage.register_tenant_upload("tenant-b", "b.pdf")

    assert tenant_storage.delete_tenant_uploads("tenant-a") == 1
    assert not (tmp_path / "a.pdf").exists()
    assert (tmp_path / "b.pdf").exists()
    assert tenant_storage._load() == {"tenant-b": ["b.pdf"]}
