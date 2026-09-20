from nightshift.bitget_private import account_from_raw, configured, status


def test_status_does_not_require_keys():
    s = status()
    assert s["orders"] is False
    assert "configured" in s
    assert configured() is s["configured"]


def test_maps_rtoken_and_btc_perp():
    raw = {
        "assets": {
            "assets": [
                {"coin": "USDT", "balance": "500", "equity": "500"},
                {"coin": "RNVDA", "balance": "40", "equity": "40", "usdValue": "8000"},
            ]
        },
        "positions": {
            "list": [
                {
                    "symbol": "BTCUSDT",
                    "posSide": "long",
                    "total": "0.1",
                    "avgPrice": "70000",
                    "markPrice": "70000",
                    "leverage": "5",
                }
            ]
        },
    }
    clocks = {
        "clocks": [{"ticker": "NVDA", "rtoken_last": 200.0, "cash_last": 200.0}],
        "btc": {"mark": 70000.0},
    }
    acct = account_from_raw(raw, clocks)
    assert acct.cash_usdt == 500
    assert acct.collaterals[0].ticker == "NVDA"
    assert abs(acct.collaterals[0].units - 40) < 1e-9
    assert acct.perps[0].symbol == "BTCUSDT"
    assert acct.perps[0].is_stock is False
    assert acct.label == "bitget_uta"


def test_ignores_dust_and_unknown_coins():
    raw = {
        "assets": {"assets": [{"coin": "DOGE", "balance": "12"}]},
        "positions": {"list": [{"symbol": "ETHUSDT", "total": "0", "posSide": "long"}]},
    }
    acct = account_from_raw(raw, None)
    assert acct.collaterals == []
    assert acct.perps == []
