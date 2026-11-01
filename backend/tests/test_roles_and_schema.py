import re
import sys
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.schema import CreateTable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.db import make_session_factory  # noqa: E402
from app.factory import create_app  # noqa: E402
from app.reconcile import ClipResult  # noqa: E402
from app.tables import Clip  # noqa: E402

BOOK_CSV = "item,location,book_qty,unit_cost\nmonitor,A1-B2,5,100\n"


def make_client(tmp_path):
    runner = lambda video, book: ClipResult(video.name, "A1-B2", "monitor", 4, False, [], "", "")  # noqa: E731
    client = TestClient(create_app("sqlite://", tmp_path / "uploads", runner, tmp_path / "out", lambda image, prompt: ""))
    client.put("/plan", files={"file": ("b.csv", BOOK_CSV, "text/csv")})
    return client


def test_the_capturer_cannot_review_their_own_clip(tmp_path):
    client = make_client(tmp_path)
    clip = client.post("/clips", files={"file": ("s.mp4", b"v", "video/mp4")}, data={"captured_by": "Ravi"}).json()
    assert clip["captured_by"] == "Ravi"
    line = {"item": "monitor", "qty": 4}
    own = client.post(f"/clips/{clip['id']}/review", json={"reviewer": " ravi ", "lines": [line]})
    assert own.status_code == 409 and "someone else" in own.json()["detail"]
    assert client.post(f"/clips/{clip['id']}/investigations", json={"reviewer": "RAVI"}).status_code == 409
    assert client.post(f"/clips/{clip['id']}/review", json={"reviewer": "Meera", "lines": [line]}).status_code == 200


def test_a_clip_with_no_named_capturer_can_be_reviewed_by_anyone(tmp_path):
    client = make_client(tmp_path)
    clip = client.post("/clips", files={"file": ("s.mp4", b"v", "video/mp4")}).json()
    assert client.post(f"/clips/{clip['id']}/review", json={"reviewer": "Meera", "lines": [{"item": "monitor", "qty": 4}]}).status_code == 200


def test_a_column_added_to_the_code_is_added_to_an_existing_table(tmp_path):
    db = tmp_path / "old.db"
    engine = create_engine(f"sqlite:///{db.as_posix()}")
    old_ddl = re.sub(r",\s*captured_by VARCHAR\(200\)", "", str(CreateTable(Clip.__table__).compile(engine)))
    assert "captured_by" not in old_ddl
    with engine.begin() as conn:
        conn.execute(text(old_ddl))
    make_session_factory(f"sqlite:///{db.as_posix()}")
    assert "captured_by" in {c["name"] for c in inspect(engine).get_columns("clips")}
