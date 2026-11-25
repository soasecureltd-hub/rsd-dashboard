"""CRUD ordering guarantees that the routes rely on."""
from app import crud, models


def _user(db, email="a@example.com"):
    user = models.User(email=email, hashed_password="x")
    db.add(user)
    db.commit()
    return user


def _assessment(db, user_id):
    a = models.Assessment(user_id=user_id, input_data={})
    db.add(a)
    db.commit()
    return a


def test_get_all_assessments_newest_first(db):
    user = _user(db)
    ids = [_assessment(db, user.id).id for _ in range(3)]
    got = [a.id for a in crud.get_all_assessments(db, user_id=user.id)]
    assert got == list(reversed(ids))


def test_get_all_assessments_limit_keeps_newest(db):
    user = _user(db)
    ids = [_assessment(db, user.id).id for _ in range(5)]
    got = [a.id for a in crud.get_all_assessments(db, user_id=user.id, limit=2)]
    assert got == [ids[4], ids[3]]


def test_get_all_assessments_scoped_to_user(db):
    alice, bob = _user(db, "alice@example.com"), _user(db, "bob@example.com")
    _assessment(db, alice.id)
    mine = _assessment(db, bob.id)
    assert [a.id for a in crud.get_all_assessments(db, user_id=bob.id)] == [mine.id]


def test_get_ai_prediction_returns_latest(db):
    user = _user(db)
    a = _assessment(db, user.id)
    for prob in (0.1, 0.5, 0.9):
        crud.create_ai_prediction(db, a.id, {}, {"unauthorized_access": prob})
    assert crud.get_ai_prediction(db, a.id).unauthorized_access_prob == 0.9


def test_get_ai_prediction_none_when_missing(db):
    assert crud.get_ai_prediction(db, 999) is None


def test_get_assessments_before(db):
    user, other = _user(db), _user(db, "b@example.com")
    ids = [_assessment(db, user.id).id for _ in range(4)]
    _assessment(db, other.id)
    got = [a.id for a in crud.get_assessments_before(db, user.id, before_id=ids[2])]
    assert got == [ids[1], ids[0]]
