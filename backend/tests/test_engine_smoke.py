import importlib


def test_pokerkit_importable():
    pk = importlib.import_module("pokerkit")
    assert pk is not None


def test_adapter_importable():
    mod = importlib.import_module("backend.adapters.engines.pokerkit_adapter")
    assert hasattr(mod, "PokerKitAdapter")
