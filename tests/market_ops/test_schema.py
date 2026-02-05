from scripts.market_ops.schema import wrap_result


def test_wrap_result_basic():
    out = wrap_result(mode="symbol", data={"x": 1}, summary=None, errors=["e"])
    assert out["meta"]["mode"] == "symbol"
    assert out["data"] == {"x": 1}
    assert out["summary"] is None
    assert out["errors"] == ["e"]
