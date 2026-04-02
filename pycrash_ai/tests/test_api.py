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


class TestPipeline:
    """Test end-to-end pipeline (mock mode)."""

    def test_pipeline_rear_end(self):
        """Pipeline should extract, lookup, simulate for a rear-end crash."""
        r = client.post("/api/v1/pipeline", json={
            "text": "Vehicle 1, a 2020 Toyota Camry, was traveling at approximately 35 mph when it struck Vehicle 2, a 2020 Honda Civic, which was stopped at a red light.",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["extraction"]["crash_type"] is not None
        assert len(data["extraction"]["vehicles"]) >= 1
        # Should have run simulation
        if data["simulation"]:
            assert data["simulation"]["delta_v1_mph"] > 0
            assert data["simulation"]["delta_v2_mph"] > 0
            assert data["summary"] is not None

    def test_pipeline_no_simulate(self):
        """Pipeline with auto_simulate=false should skip simulation."""
        r = client.post("/api/v1/pipeline", json={
            "text": "Vehicle 1 struck Vehicle 2 at an intersection.",
            "auto_simulate": False,
        })
        assert r.status_code == 200
        data = r.json()
        assert data["simulation"] is None


class TestLLMProvider:
    """Test LLM provider abstraction."""

    def test_mock_provider(self):
        """Without API keys, should use mock provider."""
        from pycrash_ai.api.agent.llm_provider import get_provider
        import os
        # Temporarily clear env vars
        old_anthropic = os.environ.pop("ANTHROPIC_API_KEY", None)
        old_openai = os.environ.pop("OPENAI_API_KEY", None)
        try:
            provider = get_provider()
            assert provider.name == "mock"
        finally:
            if old_anthropic:
                os.environ["ANTHROPIC_API_KEY"] = old_anthropic
            if old_openai:
                os.environ["OPENAI_API_KEY"] = old_openai

    def test_provider_selection_anthropic(self):
        from pycrash_ai.api.agent.llm_provider import get_provider, AnthropicProvider
        provider = get_provider(provider="anthropic", api_key="sk-ant-test")
        assert isinstance(provider, AnthropicProvider)

    def test_provider_selection_openai(self):
        from pycrash_ai.api.agent.llm_provider import get_provider, OpenAIProvider
        provider = get_provider(provider="openai", api_key="sk-test")
        assert isinstance(provider, OpenAIProvider)


class TestIngestion:
    """Test document ingestion."""

    def test_ingest_text(self):
        from pycrash_ai.api.agent.ingest import ingest_text
        long_text = "Vehicle 1, a 2020 Toyota Camry, was traveling eastbound on Main Street at approximately 35 mph when it struck Vehicle 2."
        doc = ingest_text(long_text)
        assert long_text in doc.full_text
        assert not doc.needs_vision
        assert doc.text_quality == 1.0

    def test_ingest_image(self):
        from pycrash_ai.api.agent.ingest import ingest_image
        doc = ingest_image(b"\x89PNG\r\n", "scan.png")
        assert doc.needs_vision
        assert len(doc.page_images) == 1

    def test_build_text_messages(self):
        from pycrash_ai.api.agent.ingest import ingest_text, build_extraction_messages
        doc = ingest_text("Vehicle 1 rear-ended Vehicle 2")
        messages = build_extraction_messages(doc)
        assert len(messages) == 1
        assert "Vehicle 1" in messages[0]["content"]

    def test_build_vision_messages(self):
        from pycrash_ai.api.agent.ingest import ingest_image, build_extraction_messages
        doc = ingest_image(b"\x89PNG\r\n", "scan.png")
        messages = build_extraction_messages(doc)
        assert len(messages) == 1
        # Vision messages have content blocks
        assert isinstance(messages[0]["content"], list)


class TestCaseGraph:
    """Test in-memory case graph operations."""

    def test_create_case_and_add_vehicles(self):
        from pycrash_ai.api.graph.store import InMemoryCaseStore
        store = InMemoryCaseStore()
        case = store.create_case("test-001", title="Test Case")
        case.add_scene()
        v1_id = case.add_vehicle(1, "Toyota", "Camry", 2020, role="striking")
        v2_id = case.add_vehicle(2, "Honda", "Civic", 2019, role="struck")

        vehicles = case.get_vehicles()
        assert len(vehicles) == 2
        assert vehicles[0]["make"] == "Toyota"
        assert vehicles[1]["role"] == "struck"

    def test_add_evidence_and_retrieve(self):
        from pycrash_ai.api.graph.store import InMemoryCaseStore
        store = InMemoryCaseStore()
        case = store.create_case("test-002")
        case.add_vehicle(1, "Ford", "F-150", 2021)
        case.add_evidence(
            category="speed", key="estimated_speed_mph",
            value=45, unit="mph", confidence=0.7,
            source_type="witness", applies_to_vehicle=1,
        )
        case.add_evidence(
            category="vehicle_spec", key="weight",
            value=4500, unit="lb", confidence=0.95,
            source_type="database", applies_to_vehicle=1,
        )

        evidence = case.get_evidence_for_vehicle(1)
        assert len(evidence) == 2
        assert any(e["key"] == "estimated_speed_mph" for e in evidence)
        assert any(e["key"] == "weight" for e in evidence)

    def test_find_gaps(self):
        from pycrash_ai.api.graph.store import InMemoryCaseStore
        store = InMemoryCaseStore()
        case = store.create_case("test-003")
        case.add_vehicle(1, "Toyota", "Camry", 2020)
        # Add only weight — everything else should be a gap
        case.add_evidence(
            category="vehicle_spec", key="weight",
            value=3400, unit="lb", confidence=0.95,
            applies_to_vehicle=1,
        )

        gaps = case.find_gaps()
        assert len(gaps) == 1
        assert "wb" in gaps[0]["missing"]
        assert "estimated_speed" in gaps[0]["missing"]
        assert "weight" not in gaps[0]["missing"]

    def test_find_contradictions(self):
        from pycrash_ai.api.graph.store import InMemoryCaseStore
        store = InMemoryCaseStore()
        case = store.create_case("test-004")
        case.add_vehicle(1, "Toyota", "Camry", 2020)
        case.add_evidence(
            category="speed", key="estimated_speed_mph",
            value=35, confidence=0.7, source_type="witness",
            applies_to_vehicle=1,
        )
        case.add_evidence(
            category="speed", key="estimated_speed_mph",
            value=55, confidence=0.6, source_type="police_report",
            applies_to_vehicle=1,
        )

        contradictions = case.find_contradictions()
        assert len(contradictions) == 1
        assert contradictions[0]["key"] == "estimated_speed_mph"

    def test_project_to_pycrash(self):
        from pycrash_ai.api.graph.store import InMemoryCaseStore
        store = InMemoryCaseStore()
        case = store.create_case("test-005")
        case.add_vehicle(1, "Toyota", "Camry", 2020, role="striking")
        case.add_evidence(
            category="speed", key="estimated_speed_mph",
            value=35, unit="mph", confidence=0.8,
            applies_to_vehicle=1,
        )
        case.add_evidence(
            category="vehicle_spec", key="weight",
            value=3400, unit="lb", confidence=0.95,
            applies_to_vehicle=1,
        )

        projection = case.project_to_pycrash()
        assert len(projection) == 1
        inp = projection[0]["input_dict"]
        assert inp["weight"] == 3400.0
        assert abs(inp["vx_initial"] - 35 * 1.46667) < 0.01
        assert inp["striking"] is True

    def test_export_and_format(self):
        from pycrash_ai.api.graph.store import InMemoryCaseStore
        store = InMemoryCaseStore()
        case = store.create_case("test-006", title="Export Test")
        case.add_vehicle(1, "Toyota", "Camry", 2020)
        case.add_evidence(
            category="speed", key="estimated_speed_mph",
            value=35, applies_to_vehicle=1,
        )

        export = case.export()
        assert export["format"] == "pycrash_case"
        assert export["version"] == "1.0"
        assert export["case_id"] == "test-006"
        assert len(export["vehicles"]) == 1
        assert len(export["evidence"]) == 1
        assert "projection" in export

    def test_store_list_cases(self):
        from pycrash_ai.api.graph.store import InMemoryCaseStore
        store = InMemoryCaseStore()
        store.create_case("case-a")
        store.create_case("case-b")
        cases = store.list_cases()
        assert "case-a" in cases
        assert "case-b" in cases


class TestCaseAPI:
    """Test case graph API endpoints."""

    def test_create_case(self):
        # Reset the store singleton for clean test
        from pycrash_ai.api.routes import cases
        cases._store = None

        r = client.post("/api/v1/cases", json={
            "case_id": "api-test-001",
            "title": "API Test Case",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["case_id"] == "api-test-001"
        assert data["title"] == "API Test Case"

    def test_add_vehicle_and_evidence(self):
        from pycrash_ai.api.routes import cases
        cases._store = None

        # Create case
        client.post("/api/v1/cases", json={"case_id": "api-test-002"})

        # Add vehicle
        r = client.post("/api/v1/cases/api-test-002/vehicles", json={
            "vehicle_number": 1, "make": "Toyota", "model": "Camry",
            "year": 2020, "role": "striking",
        })
        assert r.status_code == 200
        assert "vehicle_id" in r.json()

        # Add evidence
        r = client.post("/api/v1/cases/api-test-002/evidence", json={
            "category": "speed", "key": "estimated_speed_mph",
            "value": 35, "unit": "mph", "confidence": 0.7,
            "applies_to_vehicle": 1,
        })
        assert r.status_code == 200
        assert "evidence_id" in r.json()

        # Get evidence
        r = client.get("/api/v1/cases/api-test-002/evidence/1")
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["key"] == "estimated_speed_mph"

    def test_gaps_endpoint(self):
        from pycrash_ai.api.routes import cases
        cases._store = None

        client.post("/api/v1/cases", json={"case_id": "api-test-003"})
        client.post("/api/v1/cases/api-test-003/vehicles", json={
            "vehicle_number": 1, "make": "Ford", "model": "F-150",
        })

        r = client.get("/api/v1/cases/api-test-003/gaps")
        assert r.status_code == 200
        gaps = r.json()
        assert len(gaps) == 1
        assert "weight" in gaps[0]["missing"]

    def test_export_endpoint(self):
        from pycrash_ai.api.routes import cases
        cases._store = None

        client.post("/api/v1/cases", json={"case_id": "api-test-004"})
        client.post("/api/v1/cases/api-test-004/vehicles", json={
            "vehicle_number": 1, "make": "Honda", "model": "Civic",
        })

        r = client.get("/api/v1/cases/api-test-004/export")
        assert r.status_code == 200
        data = r.json()
        assert data["format"] == "pycrash_case"
        assert data["case_id"] == "api-test-004"

    def test_project_endpoint(self):
        from pycrash_ai.api.routes import cases
        cases._store = None

        client.post("/api/v1/cases", json={"case_id": "api-test-005"})
        client.post("/api/v1/cases/api-test-005/vehicles", json={
            "vehicle_number": 1, "make": "Toyota", "model": "Camry",
            "year": 2020, "role": "striking",
        })
        client.post("/api/v1/cases/api-test-005/evidence", json={
            "category": "speed", "key": "estimated_speed_mph",
            "value": 30, "unit": "mph", "confidence": 0.8,
            "applies_to_vehicle": 1,
        })

        r = client.get("/api/v1/cases/api-test-005/project")
        assert r.status_code == 200
        projection = r.json()
        assert len(projection) == 1
        assert projection[0]["input_dict"]["striking"] is True

    def test_case_not_found(self):
        from pycrash_ai.api.routes import cases
        cases._store = None

        r = client.get("/api/v1/cases/nonexistent")
        assert r.status_code == 404


class TestPipelineWithGraph:
    """Test that pipeline now builds a case graph."""

    def test_pipeline_builds_graph(self):
        from pycrash_ai.api.routes import cases
        cases._store = None

        r = client.post("/api/v1/pipeline", json={
            "text": "Vehicle 1, a 2020 Toyota Camry, was traveling at approximately 35 mph when it struck Vehicle 2, a 2020 Honda Civic, which was stopped at a red light.",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["case_id"] is not None
        assert data["graph"] is not None
        assert data["graph"]["format"] == "pycrash_case"
        assert len(data["graph"]["vehicles"]) >= 1


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
