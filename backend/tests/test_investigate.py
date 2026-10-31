import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.factory import create_app  # noqa: E402
from app.reconcile import ClipResult  # noqa: E402

BOOK_CSV = "item,location,book_qty,unit_cost\nmonitor,A1-B2,5,100\nkeyboard,A1-B2,2,50\nmonitor,A1-B4,2,100\n"


def box(i, x1, y1, x2, y2, c):
    return f"{i}<|box;x1={x1};y1={y1};x2={x2};y2={y2};w=200;h=300;c={c}|><|mask;x=0;y=0;c={c};data=zz|>"


class FakeSam:
    """Auto proposal: two sure cartons and one weak one. A click returns a box around the clicked point."""

    def __init__(self):
        self.calls: list[str] = []
        self.nothing_at_click = False
        self.sixteen = False

    def __call__(self, image, prompt):
        self.calls.append(prompt)
        if prompt == "cardboard box" and self.sixteen:
            return "<0f>" + ",".join(box(i, 0, i, 5, i + 5, 0.9) for i in range(16))
        if prompt == "cardboard box":
            return "<0f>" + ",".join([box(0, 10, 10, 90, 60, 0.95), box(1, 10, 70, 90, 120, 0.9), box(2, 10, 130, 90, 180, 0.62)])
        if self.nothing_at_click:
            return ""
        x = int(prompt.split("x=")[1].split(";")[0])
        y = int(prompt.split("y=")[1].split(";")[0])
        return "<0f>" + box(1, x - 20, y - 15, x + 20, y + 15, 0.81)


@pytest.fixture
def sam():
    return FakeSam()


@pytest.fixture
def env(tmp_path, sam):
    out = tmp_path / "out"

    def runner(video, book):
        (out / "evidence").mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (200, 300), "white").save(out / "evidence" / f"{video.stem}_raw.png")
        return ClipResult(video.name, None, None, 3, True, ["location not recognised from narration"], "evidence/x_review.png", "shelf")

    client = TestClient(create_app("sqlite://", tmp_path / "uploads", runner, out, sam))
    client.put("/plan", files={"file": ("b.csv", BOOK_CSV, "text/csv")})
    clip = client.post("/clips", files={"file": ("s.mp4", b"video", "video/mp4")}).json()
    return client, clip["id"]


def start(client, clip_id, **extra):
    return client.post(f"/clips/{clip_id}/investigations", json={"reviewer": "ana", **extra})


def test_sam_proposals_start_included_only_when_confident(env, sam):
    client, clip_id = env
    inv = start(client, clip_id).json()
    assert [(o["id"], o["included"]) for o in inv["objects"]] == [(0, True), (1, True), (2, False)]
    assert inv["machine_count"] == 3 and (inv["frame_w"], inv["frame_h"]) == (200, 300)
    assert inv["capped"] is False and inv["events"][0]["action"] == "started"
    assert client.get(f"/investigations/{inv['id']}/frame").headers["content-type"] == "image/png"


def test_sam_reaching_its_object_limit_is_flagged(env, sam):
    client, clip_id = env
    sam.sixteen = True
    assert start(client, clip_id).json()["capped"] is True


def test_click_adds_the_object_under_the_point(env, sam):
    client, clip_id = env
    inv = start(client, clip_id).json()
    after = client.post(f"/investigations/{inv['id']}/clicks", json={"x": 100, "y": 200}).json()
    added = after["objects"][-1]
    assert (added["id"], added["source"], added["box"], added["included"]) == (100, "click", [80, 185, 120, 215], True)
    assert sam.calls[-1] == "<0f>1<|point;x=100;y=200;w=200;h=300|>"
    assert client.post(f"/investigations/{inv['id']}/clicks", json={"x": 500, "y": 5}).status_code == 422
    sam.nothing_at_click = True
    assert client.post(f"/investigations/{inv['id']}/clicks", json={"x": 5, "y": 5}).status_code == 422


def test_edits_are_logged_and_validated(env):
    client, clip_id = env
    inv = start(client, clip_id).json()
    url = f"/investigations/{inv['id']}/objects/2"
    assert client.patch(url, json={"included": True, "item": "keyboard"}).status_code == 200
    assert client.patch(url, json={"item": "toaster"}).status_code == 422
    assert client.patch(f"/investigations/{inv['id']}/objects/99", json={"included": False}).status_code == 404
    events = client.get(f"/investigations/{inv['id']}").json()["events"]
    assert [e["action"] for e in events] == ["started", "object_changed"]
    assert events[1]["detail"] == {"object": 2, "included": True, "item": "keyboard"}


def test_confirmed_investigation_becomes_the_clips_review(env):
    client, clip_id = env
    inv = start(client, clip_id, location="A1-B2").json()
    base = f"/investigations/{inv['id']}"
    body = {"outcome": "confirmed"}
    assert client.post(f"{base}/resolve", json=body).status_code == 422  # included cartons have no item yet
    for obj_id, item in ((0, "monitor"), (1, "monitor")):
        client.patch(f"{base}/objects/{obj_id}", json={"item": item})
    client.patch(f"{base}/objects/2", json={"included": True, "item": "keyboard"})
    done = client.post(f"{base}/resolve", json={**body, "note": "third carton was a keyboard"}).json()
    assert (done["status"], done["counts"]["per_item"]) == ("resolved", {"monitor": 2, "keyboard": 1})
    assert client.patch(f"{base}/objects/0", json={"included": False}).status_code == 409
    rows = {(r["location"], r["item"]): r for r in client.get("/reconciliation").json() if r["location"] == "A1-B2"}
    assert (rows[("A1-B2", "monitor")]["counted_qty"], rows[("A1-B2", "monitor")]["variance_qty"]) == (2, -3)
    assert (rows[("A1-B2", "keyboard")]["counted_qty"], rows[("A1-B2", "keyboard")]["reviewer"]) == (1, "ana")
    clip = client.get(f"/clips/{clip_id}").json()
    assert clip["review"]["lines"][0]["note"] == f"investigation {inv['id']}" and clip["location"] == "A1-B2"


def test_confirming_needs_a_location_and_at_least_one_carton(env):
    client, clip_id = env
    inv = start(client, clip_id).json()
    assert client.post(f"/investigations/{inv['id']}/resolve", json={"outcome": "confirmed"}).status_code == 422
    assert start(client, clip_id, location="Z9-Z9").status_code == 422
    resolved = client.post(f"/investigations/{inv['id']}/resolve", json={"outcome": "unresolved", "note": "shelf was blocked"}).json()
    assert resolved["outcome"] == "unresolved" and client.get(f"/clips/{clip_id}").json()["review"] is None


def test_unknown_ids(env):
    client, _ = env
    assert client.post("/clips/nope/investigations", json={"reviewer": "ana"}).status_code == 404
    assert client.get("/investigations/nope").status_code == 404
    assert client.get("/clips/nope/investigations").json() == []
