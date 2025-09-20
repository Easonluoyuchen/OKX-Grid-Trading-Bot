# src/main.py
import os, argparse, math
from dotenv import load_dotenv
from src.config.loader import load_config
from src.exchange.okx_client import build_okx
from src.engine import GridEngine

def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="configs/config.local.yml")
    return ap.parse_args()

def make_levels(lower: float, upper: float, levels: int, snap_price):
    if levels <= 1:
        return [snap_price(lower), snap_price(upper)]
    step = (upper - lower) / (levels - 1)
    arr = [snap_price(lower + i * step) for i in range(levels)]
    arr = sorted(set(arr))
    return arr

def main():
    load_dotenv(override=True)
    args = parse_args()
    cfg = load_config(args.config)

    # ---- OKX ----
    api_key = os.environ.get("OKX_API_KEY")
    api_secret = os.environ.get("OKX_API_SECRET")
    passphrase = os.environ.get("OKX_PASS")
    use_testnet = str(os.environ.get("OKX_USE_TESTNET", "false")).lower() == "true"
    default_type = (cfg.get("exchange") or {}).get("default_type", "swap")
    symbol = (cfg.get("exchange") or {}).get("symbol", "BTC-USDT-SWAP")

    okx = build_okx(api_key, api_secret, passphrase, use_testnet=use_testnet, default_type=default_type)
    okx.load_markets()
    mkt = okx.market(symbol)

    # 精度函数
    snap_price = lambda p: float(okx.price_to_precision(symbol, p))

    # 合约面值（示例：USDT 合约面值通常等价 1 张=1 张名义，按你的市场调整）
    contract_size = float(mkt.get("contractSize") or 1.0)

    # ---- 网格参数 ----
    g = cfg.get("grid") or {}
    lower = float(g.get("lower_price", 52000))
    upper = float(g.get("upper_price", 62000))
    nlev = int(g.get("levels", 40))
    order_size = float(g.get("order_size", 20))  # 每格名义金额（USDT）

    levels = make_levels(lower, upper, nlev, snap_price)

    # 用名义金额换算合约数量（近似：qty = 名义/价格/contract_size）
    # 也可以在配置里直接给每格合约数量，这里给默认策略
    grid_qty_by_level = {}
    mid = (lower + upper) / 2.0
    for p in levels:
        contracts = max(0.0, order_size / max(p, 1e-9) / contract_size)
        # 数量精度留给 engine.safe_place 再校正
        grid_qty_by_level[p] = contracts

    # 进场参考价（可用 mid 或当前 mark）
    # 这里用 ticker 的近似，engine 内部会进一步获取
    try:
        tk = okx.fetch_ticker(symbol)
        entry_price = float(tk.get("last") or mid)
    except Exception:
        entry_price = mid

    # 下单函数（注入）
    def place_limit(side: str, price: float, qty: float):
        params = {'tdMode': 'cross'}
        return okx.create_order(symbol, 'limit', side, qty, price, params)

    engine = GridEngine(
        okx=okx,
        symbol=symbol,
        mkt=mkt,
        entry_price=entry_price,
        contract_size=contract_size,
        levels=levels,
        grid_qty_by_level=grid_qty_by_level,
        place_limit=place_limit,
        snap_price=snap_price,
        state_path=(cfg.get("runtime") or {}).get("state_path", "grid_state.json"),
        commands_path=(cfg.get("runtime") or {}).get("commands_path", "grid_commands.jsonl"),
        fee_rate=float((cfg.get("runtime") or {}).get("fee_rate", 0.0005)),
        sleep_sec=float((cfg.get("runtime") or {}).get("sleep_sec", 0.5)),
        loop_sleep=float((cfg.get("runtime") or {}).get("rest_poll_sec", 2.0)),
        band_ttl=float((cfg.get("runtime") or {}).get("band_ttl", 8.0)),
        init_position=bool((cfg.get("grid") or {}).get("init_position", False)),
    )

    engine.run_forever(heartbeat_every=int((cfg.get("runtime") or {}).get("ws_heartbeat_sec", 20)))

if __name__ == "__main__":
    main()
