"""Test package."""

import os

# Runs before any test module is imported. The engine is created the first time the models are imported,
# so a module that sets DATABASE_URL itself is too late whenever an earlier one imported them: a full run
# then wrote its rows to the real market.db. Modules that need their own database still set it themselves.
os.environ["DATABASE_URL"] = "sqlite://"
