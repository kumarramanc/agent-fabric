"""Check the single demo dataset without copying or resetting it."""

from pathlib import Path
import json


def validate_data():
    directory = Path(__file__).resolve().parent / "data"
    with open(directory / "customer_orders.json", encoding="utf-8") as file:
        orders = json.load(file)
    if not isinstance(orders, list):
        raise ValueError("Orders must be a JSON list.")
    policy_files = list((directory / "policies").rglob("*.txt"))
    if not policy_files:
        raise ValueError("No policy files found.")
    print("Dataset ready:", len(orders), "orders and", len(policy_files), "policy documents.")


if __name__ == "__main__":
    validate_data()
