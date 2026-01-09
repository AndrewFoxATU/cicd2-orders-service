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

    tyre_status = 200
    tyre_qty = 10
    tyre_price = "135.00"

    patch_status = 200  # stock update

    def __init__(self, timeout=None):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url: str):
        if "/api/users/" in url:
            if self.user_status == 200:
                return FakeResp(200, {"id": 1, "name": self.user_name})
            return FakeResp(self.user_status, {})

        if "/api/tyres/" in url:
            if self.tyre_status == 200:
                return FakeResp(200, {"id": 10, "quantity": self.tyre_qty, "retail_cost": self.tyre_price})
            return FakeResp(self.tyre_status, {})

        return FakeResp(500, {})

    async def patch(self, url: str, json: dict):
        return FakeResp(self.patch_status, {})




def _use_fakes(monkeypatch):
    monkeypatch.setattr(main_mod.httpx, "AsyncClient", lambda timeout=8.0: FakeAsyncClient(timeout=timeout))


    async def fake_publish_message(routing_key: str, payload: dict):
        return None

    monkeypatch.setattr(main_mod, "publish_message", fake_publish_message)


# Tests

def test_sell_happy_path(client, monkeypatch):
    _use_fakes(monkeypatch)

    # user 200, tyre qty=10, price=135, patch 200
    r = client.post("/api/sell", json={"seller_user_id": 1, "tyre_id": 10, "quantity": 3})
    assert r.status_code == 200, r.text

    data = r.json()
    assert data["seller_user_id"] == 1
    assert data["seller_name"] == "Alice"
    assert data["tyre_id"] == 10
    assert data["quantity"] == 3
    assert str(data["total_charge"]) == "405.00"  # 135.00 * 3


def test_sell_bad_quantity_returns_400(client, monkeypatch):
    _use_fakes(monkeypatch)

    r = client.post("/api/sell", json={"seller_user_id": 1, "tyre_id": 10, "quantity": 0})
    assert r.status_code == 400
    assert r.json()["detail"] == "Quantity must be > 0"


def test_sell_seller_not_found_returns_404(client, monkeypatch):
    _use_fakes(monkeypatch)
    FakeAsyncClient.user_status = 404

    r = client.post("/api/sell", json={"seller_user_id": 999, "tyre_id": 10, "quantity": 1})
    assert r.status_code == 404
    assert r.json()["detail"] == "Seller not found"

    FakeAsyncClient.user_status = 200


def test_sell_not_enough_stock_returns_409(client, monkeypatch):
    _use_fakes(monkeypatch)
    FakeAsyncClient.tyre_qty = 2

    r = client.post("/api/sell", json={"seller_user_id": 1, "tyre_id": 10, "quantity": 3})
    assert r.status_code == 409
    assert r.json()["detail"] == "Not enough stock"

    # reset
    FakeAsyncClient.tyre_qty = 10


def test_sell_patch_failure_returns_502(client, monkeypatch):
    _use_fakes(monkeypatch)
    FakeAsyncClient.patch_status = 500

    r = client.post("/api/sell", json={"seller_user_id": 1, "tyre_id": 10, "quantity": 1})
    assert r.status_code == 502
    assert r.json()["detail"] == "Failed to update stock"

    # reset
    FakeAsyncClient.patch_status = 200
