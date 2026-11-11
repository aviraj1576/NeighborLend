from uuid import UUID, uuid4


def test_id_collision_never_overwrites_or_deletes_existing_evidence(
    client, application, upload, image_bytes, headers, monkeypatch
):
    original = image_bytes()
    record = upload(data=original).json()
    monkeypatch.setattr("ep_engine.services.evidence.uuid4", lambda: UUID(record["id"]))
    response = upload(data=image_bytes(color="green"))
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "identifier_conflict"
    assert client.get(f"/v1/evidence/{record['id']}/content", headers=headers).content == original


def test_unreferenced_existing_file_is_not_overwritten_by_upload(
    client, application, upload, monkeypatch
):
    evidence_id = uuid4()
    original = application.state.storage.root / f"{evidence_id}.original"
    original.write_bytes(b"preexisting orphan")
    monkeypatch.setattr("ep_engine.services.evidence.uuid4", lambda: evidence_id)
    response = upload()
    assert response.status_code == 409
    assert original.read_bytes() == b"preexisting orphan"
