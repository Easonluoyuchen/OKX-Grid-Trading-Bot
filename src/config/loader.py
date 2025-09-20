# src/config/loader.py
import yaml

def load_config(path: str) -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f) or {}
