# src/exchange/okx_client.py
import ccxt

def build_okx(api_key, api_secret, passphrase, use_testnet=False, default_type="swap"):
    okx = ccxt.okx({
        "apiKey": api_key,
        "secret": api_secret,
        "password": passphrase,
        "enableRateLimit": True,
        "options": {"defaultType": default_type},
    })
    okx.set_sandbox_mode(bool(use_testnet))
    return okx
