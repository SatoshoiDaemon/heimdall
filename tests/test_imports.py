import importlib


def test_application_modules_import_without_external_connections():
    modules = [
        "src.core.bot",
        "src.cogs.events",
        "src.cogs.verification",
        "src.cogs.config_ui",
        "src.services.config_service",
        "src.services.moderation_service",
    ]

    for module in modules:
        assert importlib.import_module(module) is not None
