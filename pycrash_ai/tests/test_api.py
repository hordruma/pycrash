"""Tests for PycrashAI API endpoints.

Run with: pytest platform/tests/ -v
Or via Docker: docker compose run api pytest platform/tests/ -v
"""
import pytest
from fastapi.testclient import TestClient

from pycrash_ai.api.main import app

client = TestClient(app)


class TestHealthAndRoot:

    def test_root(self):
        r = client.get("/")
        assert r.status_code == 200
        data = r.json()
        assert data["name"] == "PycrashAI"
        assert data["status"] == "running"

    def test_health(self):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "healthy"

    def test_docs_available(self):
        r = client.get("/docs")
        assert r.status_code == 200


class TestSDOFSync:
    """Test synchronous SDOF simulation endpoint."""

    def test_basic_sdof(self):
        """Two equal cars, 30 mph striking stationary."""
        r = client.post("/api/v1/simulate/sdof/sync", json={
            "w1": 3400, "w2": 3400,
            "v1": 30, "v2": 0,
            "cor": 0.15, "k": 50000, "tstop": 0.5,
        })
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "complete"
        assert data["delta_v1_mph"] > 0
        assert data["delta_v2_mph"] > 0
        # Momentum should be conserved
        assert data["momentum_conserved"] < 1.0

    def test_heavier_striking(self):
        """Heavier vehicle should have smaller delta-V."""
        r = client.post("/api/v1/simulate/sdof/sync", json={
            "w1": 5000, "w2": 2500,
            "v1": 30, "v2": 0,
            "cor": 0.15, "k": 50000, "tstop": 0.5,
        })
        data = r.json()
        assert data["delta_v1_mph"] < data["delta_v2_mph"]

    def test_equal_weight_elastic(self):
        """Equal weight, COR=1: delta-Vs should be equal."""
        r = client.post("/api/v1/simulate/sdof/sync", json={
            "w1": 3000, "w2": 3000,
            "v1": 30, "v2": 0,
            "cor": 1.0, "k": 50000, "tstop": 1.0,
        })
        data = r.json()
        assert abs(data["delta_v1_mph"] - data["delta_v2_mph"]) < 1.0

    def test_validation_rejects_bad_input(self):
        """Should reject negative weight."""
        r = client.post("/api/v1/simulate/sdof/sync", json={
            "w1": -100, "w2": 3000,
            "v1": 30, "v2": 0,
            "cor": 0.15, "k": 50000, "tstop": 0.5,
        })
        assert r.status_code == 422

    def test_validation_rejects_bad_cor(self):
        """Should reject COR > 1."""
        r = client.post("/api/v1/simulate/sdof/sync", json={
            "w1": 3000, "w2": 3000,
            "v1": 30, "v2": 0,
            "cor": 1.5, "k": 50000, "tstop": 0.5,
        })
        assert r.status_code == 422


class TestExtraction:
    """Test extraction endpoint (mock mode without API key)."""

    def test_basic_extraction(self):
        r = client.post("/api/v1/extract", json={
            "text": "Vehicle 1, a 2020 Toyota Camry, was traveling eastbound at approximately 35 mph when it struck Vehicle 2, a 2019 Honda Civic, which was stopped at a red light. Vehicle 1 left 45 feet of skid marks prior to impact.",
        })
        assert r.status_code == 200
        data = r.json()
        assert len(data["vehicles"]) >= 1
        assert data["crash_type"] is not None

    def test_intersection_detection(self):
        r = client.post("/api/v1/extract", json={
            "text": "The crash occurred at the intersection of Main St and Oak Ave. Vehicle 1 was turning left when struck by Vehicle 2.",
        })
        data = r.json()
        assert data["crash_type"] == "intersection_angle"

    def test_sideswipe_detection(self):
        r = client.post("/api/v1/extract", json={
            "text": "Vehicle 1 made a sideswipe contact with Vehicle 2 while changing lanes on the highway.",
        })
        data = r.json()
        assert data["crash_type"] == "sideswipe_same"


class TestVehicleLookup:
    """Test vehicle database lookup."""

    def test_lookup_by_make(self):
        r = client.get("/api/v1/vehicles/lookup?make=Toyota")
        assert r.status_code == 200
        data = r.json()
        assert len(data) > 0
        assert all(v["make"] == "Toyota" for v in data)

    def test_lookup_by_make_model(self):
        r = client.get("/api/v1/vehicles/lookup?make=Toyota&model=Camry")
        assert r.status_code == 200
        data = r.json()
        assert len(data) > 0
        assert data[0]["weight"] > 0
        assert data[0]["wb"] > 0

    def test_lookup_not_found(self):
        r = client.get("/api/v1/vehicles/lookup?make=Nonexistent&model=Car")
        assert r.status_code == 404

    def test_list_makes(self):
        r = client.get("/api/v1/vehicles/makes")
        assert r.status_code == 200
        makes = r.json()
        assert "Toyota" in makes
        assert "Ford" in makes
