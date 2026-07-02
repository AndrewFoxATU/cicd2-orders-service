import sqlalchemy.orm

import app.main as main_mod

class FakeResp:
    def __init__(self, status_code: int, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


class FakeAsyncClient:
    user_status = 200
    user_name = "Alice"

    # status returned by the atomic stock endpoint
    stock_status = 200
    tyre_qty_after = 7
    tyre_price = "135.00"

    calls = []  # (method, url, json, has_auth)

    def __init__(self, timeout=None):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url: str, headers=None):
        FakeAsyncClient.calls.append(("GET", url, None, bool(headers and headers.get("Authorization"))))
        if "/api/users/" in url:
            if self.user_status == 200:
                return FakeResp(200, {"id": 1, "name": self.user_name})
            return FakeResp(self.user_status, {})
        return FakeResp(500, {})

    async def post(self, url: str, json: dict, headers=None):
        FakeAsyncClient.calls.append(("POST", url, json, bool(headers and headers.get("Authorization"))))
        if url.endswith("/stock"):
            if self.stock_status == 200:
                return FakeResp(200, {
                    "id": 10,
                    "quantity": self.tyre_qty_after,
                    "retail_cost": self.tyre_price,
                })
            return FakeResp(self.stock_status, {})
        return FakeResp(500, {})




def _use_fakes(monkeypatch):
    FakeAsyncClient.calls = []
    FakeAsyncClient.user_status = 200
    FakeAsyncClient.stock_status = 200
    monkeypatch.setattr(main_mod.httpx, "AsyncClient", lambda timeout=8.0: FakeAsyncClient(timeout=timeout))


    async def fake_publish_message(routing_key: str, payload: dict):
        return None

    monkeypatch.setattr(main_mod, "publish_message", fake_publish_message)


def _stock_calls():
    return [c for c in FakeAsyncClient.calls if c[0] == "POST" and c[1].endswith("/stock")]


# Tests

def test_sell_happy_path(client, monkeypatch, seller_headers):
    _use_fakes(monkeypatch)

    r = client.post(
        "/api/sell",
        json={"seller_user_id": 1, "tyre_id": 10, "quantity": 3},
        headers=seller_headers,
    )
    assert r.status_code == 200, r.text

    data = r.json()
    assert data["seller_user_id"] == 1
    assert data["seller_name"] == "Alice"
    assert data["tyre_id"] == 10
    assert data["quantity"] == 3
    assert str(data["total_charge"]) == "405.00"  # 135.00 * 3

    # exactly one atomic decrement, carrying a service token
    stock = _stock_calls()
    assert len(stock) == 1
    assert stock[0][2] == {"delta": -3}
    assert stock[0][3] is True  # Authorization header present


def test_sell_requires_auth(client, monkeypatch):
    _use_fakes(monkeypatch)

    r = client.post("/api/sell", json={"seller_user_id": 1, "tyre_id": 10, "quantity": 1})
    assert r.status_code == 401


def test_sell_as_another_user_is_forbidden(client, monkeypatch, other_seller_headers):
    _use_fakes(monkeypatch)

    r = client.post(
        "/api/sell",
        json={"seller_user_id": 1, "tyre_id": 10, "quantity": 1},
        headers=other_seller_headers,
    )
    assert r.status_code == 403
    assert r.json()["detail"] == "Cannot sell as another user"


def test_admin_can_sell_on_behalf_of_user(client, monkeypatch, admin_headers):
    _use_fakes(monkeypatch)

    r = client.post(
        "/api/sell",
        json={"seller_user_id": 1, "tyre_id": 10, "quantity": 1},
        headers=admin_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["seller_user_id"] == 1


def test_sell_bad_quantity_returns_400(client, monkeypatch, seller_headers):
    _use_fakes(monkeypatch)

    r = client.post(
        "/api/sell",
        json={"seller_user_id": 1, "tyre_id": 10, "quantity": 0},
        headers=seller_headers,
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "Quantity must be > 0"


def test_sell_seller_not_found_returns_404(client, monkeypatch, admin_headers):
    _use_fakes(monkeypatch)
    FakeAsyncClient.user_status = 404

    r = client.post(
        "/api/sell",
        json={"seller_user_id": 999, "tyre_id": 10, "quantity": 1},
        headers=admin_headers,
    )
    assert r.status_code == 404
    assert r.json()["detail"] == "Seller not found"

    # stock was never touched
    assert _stock_calls() == []


def test_sell_tyre_not_found_returns_404(client, monkeypatch, seller_headers):
    _use_fakes(monkeypatch)
    FakeAsyncClient.stock_status = 404

    r = client.post(
        "/api/sell",
        json={"seller_user_id": 1, "tyre_id": 999, "quantity": 1},
        headers=seller_headers,
    )
    assert r.status_code == 404
    assert r.json()["detail"] == "Tyre not found"


def test_sell_not_enough_stock_returns_409(client, monkeypatch, seller_headers):
    _use_fakes(monkeypatch)
    FakeAsyncClient.stock_status = 409

    r = client.post(
        "/api/sell",
        json={"seller_user_id": 1, "tyre_id": 10, "quantity": 3},
        headers=seller_headers,
    )
    assert r.status_code == 409
    assert r.json()["detail"] == "Not enough stock"


def test_sell_stock_service_error_returns_502(client, monkeypatch, seller_headers):
    _use_fakes(monkeypatch)
    FakeAsyncClient.stock_status = 500

    r = client.post(
        "/api/sell",
        json={"seller_user_id": 1, "tyre_id": 10, "quantity": 1},
        headers=seller_headers,
    )
    assert r.status_code == 502
    assert r.json()["detail"] == "Failed to update stock"


def test_sell_restores_stock_when_sale_cannot_be_saved(client, monkeypatch, seller_headers):
    _use_fakes(monkeypatch)

    def failing_commit(self):
        raise RuntimeError("database down")

    monkeypatch.setattr(sqlalchemy.orm.Session, "commit", failing_commit)

    r = client.post(
        "/api/sell",
        json={"seller_user_id": 1, "tyre_id": 10, "quantity": 2},
        headers=seller_headers,
    )
    assert r.status_code == 502
    assert r.json()["detail"] == "Failed to record sale; stock restored"

    # decrement followed by a compensating restore
    stock = _stock_calls()
    assert [c[2] for c in stock] == [{"delta": -2}, {"delta": 2}]


def test_sell_succeeds_even_if_event_publish_fails(client, monkeypatch, seller_headers):
    _use_fakes(monkeypatch)

    async def broken_publish(routing_key: str, payload: dict):
        raise ConnectionError("broker unreachable")

    monkeypatch.setattr(main_mod, "publish_message", broken_publish)

    r = client.post(
        "/api/sell",
        json={"seller_user_id": 1, "tyre_id": 10, "quantity": 1},
        headers=seller_headers,
    )
    assert r.status_code == 200, r.text

    # no compensation happened — the sale stands
    assert [c[2] for c in _stock_calls()] == [{"delta": -1}]
