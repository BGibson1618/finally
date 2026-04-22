"""Tests for market data source factory."""

import os
from unittest.mock import patch

import pytest

from app import config
from app.market.cache import PriceCache
from app.market.factory import create_market_data_source
from app.market.massive_client import MassiveDataSource
from app.market.simulator import SimulatorDataSource


@pytest.fixture(autouse=True)
def clear_settings_cache():
    """Settings is lru_cached; invalidate before and after each test."""
    config.get_settings.cache_clear()
    yield
    config.get_settings.cache_clear()


class TestFactory:
    """Tests for create_market_data_source factory."""

    def test_creates_simulator_when_no_api_key(self):
        cache = PriceCache()
        with patch.dict(os.environ, {}, clear=True):
            config.get_settings.cache_clear()
            source = create_market_data_source(cache)
        assert isinstance(source, SimulatorDataSource)

    def test_creates_simulator_when_api_key_empty(self):
        cache = PriceCache()
        with patch.dict(os.environ, {"MASSIVE_API_KEY": ""}, clear=True):
            config.get_settings.cache_clear()
            source = create_market_data_source(cache)
        assert isinstance(source, SimulatorDataSource)

    def test_creates_simulator_when_api_key_whitespace(self):
        cache = PriceCache()
        with patch.dict(os.environ, {"MASSIVE_API_KEY": "   "}, clear=True):
            config.get_settings.cache_clear()
            source = create_market_data_source(cache)
        assert isinstance(source, SimulatorDataSource)

    def test_creates_massive_when_api_key_set(self):
        cache = PriceCache()
        with patch.dict(os.environ, {"MASSIVE_API_KEY": "test-key"}, clear=True):
            config.get_settings.cache_clear()
            source = create_market_data_source(cache)
        assert isinstance(source, MassiveDataSource)

    def test_massive_receives_api_key(self):
        cache = PriceCache()
        with patch.dict(os.environ, {"MASSIVE_API_KEY": "test-key-123"}, clear=True):
            config.get_settings.cache_clear()
            source = create_market_data_source(cache)
        assert isinstance(source, MassiveDataSource)
        assert source._api_key == "test-key-123"

    def test_simulator_receives_cache(self):
        cache = PriceCache()
        with patch.dict(os.environ, {}, clear=True):
            config.get_settings.cache_clear()
            source = create_market_data_source(cache)
        assert isinstance(source, SimulatorDataSource)
        assert source._cache is cache

    def test_massive_receives_cache(self):
        cache = PriceCache()
        with patch.dict(os.environ, {"MASSIVE_API_KEY": "test-key"}, clear=True):
            config.get_settings.cache_clear()
            source = create_market_data_source(cache)
        assert isinstance(source, MassiveDataSource)
        assert source._cache is cache
