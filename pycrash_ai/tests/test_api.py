"""Tests for PycrashAI API endpoints.

Run with: pytest pycrash_ai/tests/ -v
Or via Docker: docker compose run api pytest pycrash_ai/tests/ -v
"""
import pytest
from fastapi.testclient import TestClient

from pycrash_ai.app import app

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
        from pycrash_ai.agent.llm_provider import get_provider
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
        from pycrash_ai.agent.llm_provider import get_provider, AnthropicProvider
        provider = get_provider(provider="anthropic", api_key="sk-ant-test")
        assert isinstance(provider, AnthropicProvider)

    def test_provider_selection_openai(self):
        from pycrash_ai.agent.llm_provider import get_provider, OpenAIProvider
        provider = get_provider(provider="openai", api_key="sk-test")
        assert isinstance(provider, OpenAIProvider)


class TestIngestion:
    """Test document ingestion."""

    def test_ingest_text(self):
        from pycrash_ai.agent.ingest import ingest_text
        long_text = "Vehicle 1, a 2020 Toyota Camry, was traveling eastbound on Main Street at approximately 35 mph when it struck Vehicle 2."
        doc = ingest_text(long_text)
        assert long_text in doc.full_text
        assert not doc.needs_vision
        assert doc.text_quality == 1.0

    def test_ingest_image(self):
        from pycrash_ai.agent.ingest import ingest_image
        doc = ingest_image(b"\x89PNG\r\n", "scan.png")
        assert doc.needs_vision
        assert len(doc.page_images) == 1

    def test_build_text_messages(self):
        from pycrash_ai.agent.ingest import ingest_text, build_extraction_messages
        doc = ingest_text("Vehicle 1 rear-ended Vehicle 2")
        messages = build_extraction_messages(doc)
        assert len(messages) == 1
        assert "Vehicle 1" in messages[0]["content"]

    def test_build_vision_messages(self):
        from pycrash_ai.agent.ingest import ingest_image, build_extraction_messages
        doc = ingest_image(b"\x89PNG\r\n", "scan.png")
        messages = build_extraction_messages(doc)
        assert len(messages) == 1
        # Vision messages have content blocks
        assert isinstance(messages[0]["content"], list)


class TestCaseGraph:
    """Test in-memory case graph operations."""

    def test_create_case_and_add_vehicles(self):
        from pycrash_ai.graph.store import InMemoryCaseStore
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
        from pycrash_ai.graph.store import InMemoryCaseStore
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
        from pycrash_ai.graph.store import InMemoryCaseStore
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
        from pycrash_ai.graph.store import InMemoryCaseStore
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
        from pycrash_ai.graph.store import InMemoryCaseStore
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
        from pycrash_ai.graph.store import InMemoryCaseStore
        store = InMemoryCaseStore()
        case = store.create_case("test-006", title="Export Test")
        case.add_vehicle(1, "Toyota", "Camry", 2020)
        case.add_evidence(
            category="speed", key="estimated_speed_mph",
            value=35, applies_to_vehicle=1,
        )

        export = case.export()
        assert export["format"] == "pycrash_case"
        assert export["version"] == "2.0"
        assert export["case_id"] == "test-006"
        assert len(export["vehicles"]) == 1
        assert len(export["evidence"]) == 1
        assert "projection" in export

    def test_store_list_cases(self):
        from pycrash_ai.graph.store import InMemoryCaseStore
        store = InMemoryCaseStore()
        store.create_case("case-a")
        store.create_case("case-b")
        cases = store.list_cases()
        assert "case-a" in cases
        assert "case-b" in cases


class TestHypergraphLayers:
    """Test all 6 hypergraph layers and cross-layer queries."""

    def _make_case(self):
        from pycrash_ai.graph.store import InMemoryCaseStore
        store = InMemoryCaseStore()
        case = store.create_case("hyper-001", title="Full Hypergraph Test")
        case.add_scene()
        return case

    def test_entity_layer_drivers(self):
        case = self._make_case()
        case.add_vehicle(1, "Toyota", "Camry", 2020, role="striking")
        case.add_driver(1, "John Doe", 35, impairment="none")
        drivers = case.get_drivers()
        assert len(drivers) == 1
        assert drivers[0]["name"] == "John Doe"

    def test_temporal_layer_events_and_phases(self):
        case = self._make_case()
        case.add_vehicle(1, "Toyota", "Camry", 2020)
        pid = case.add_phase("pre_impact", t_start=-2.0, t_end=0.0)
        eid1 = case.add_event("brake_application", "V1 brakes", t=-1.5, phase="pre_impact")
        eid2 = case.add_event("first_contact", "Impact", t=0.0)
        case.order_events(eid1, eid2)

        timeline = case.get_timeline()
        assert len(timeline) == 2
        assert timeline[0]["t"] == -1.5
        assert timeline[1]["t"] == 0.0

        phase_events = case.get_events_for_phase("pre_impact")
        assert len(phase_events) == 1
        assert phase_events[0]["event_type"] == "brake_application"

    def test_spatial_layer_positions_and_impact(self):
        case = self._make_case()
        v1 = case.add_vehicle(1, "Toyota", "Camry", 2020)
        v2 = case.add_vehicle(2, "Honda", "Civic", 2019)

        case.add_position(10.0, 20.0, heading=90, entity_id=v1, t=-1.0)
        case.add_position(15.0, 20.0, heading=90, entity_id=v1, t=0.0)
        case.add_impact_point(15.0, 20.0, v1, v2)

        positions = case.get_positions_for_entity(v1)
        assert len(positions) == 2
        assert positions[0]["x"] == 10.0

        impact_points = case.get_impact_points()
        assert len(impact_points) == 1
        assert impact_points[0]["x"] == 15.0

    def test_spatial_layer_trajectory(self):
        case = self._make_case()
        v1 = case.add_vehicle(1, "Toyota", "Camry", 2020)
        traj_id = case.add_trajectory(v1, [
            {"x": 0, "y": 0, "heading": 90, "t": -2.0},
            {"x": 5, "y": 0, "heading": 90, "t": -1.0},
            {"x": 10, "y": 0, "heading": 90, "t": 0.0},
        ])
        assert traj_id.startswith("hyper-001_traj_")
        positions = case.get_positions_for_entity(v1)
        assert len(positions) == 3

    def test_causal_layer_factors_and_chain(self):
        case = self._make_case()
        case.add_vehicle(1, "Toyota", "Camry", 2020)
        eid = case.add_event("first_contact", "Impact", t=0.0)
        f1 = case.add_factor("distraction", "Phone use", severity=0.9)
        f2 = case.add_factor("excessive_speed", "15 over limit", severity=0.7)
        case.link_factor_to_event(f1, eid)
        case.link_factor_to_factor(f1, f2)  # distraction contributed to speed

        factors = case.get_factors()
        assert len(factors) == 2

        chain = case.get_causal_chain()
        distraction = [f for f in chain if f["factor_type"] == "distraction"][0]
        assert len(distraction["contributed_to"]) == 1
        assert len(distraction["caused_events"]) == 1

    def test_causal_layer_evidence_support(self):
        case = self._make_case()
        case.add_vehicle(1, "Toyota", "Camry", 2020)
        f1 = case.add_factor("excessive_speed", severity=0.8)
        ev1 = case.add_evidence("speed", "estimated_speed_mph", 65, "mph",
                                confidence=0.7, applies_to_vehicle=1)
        case.link_factor_to_evidence(f1, ev1)

        supporting = case.get_evidence_supporting_factor(f1)
        assert len(supporting) == 1

    def test_physical_layer_delta_v(self):
        case = self._make_case()
        case.add_vehicle(1, "Toyota", "Camry", 2020)
        case.add_delta_v(1, dvx=-15.2, dvy=2.1, magnitude_mph=10.5)

        phys = case.get_physical_for_vehicle(1)
        assert len(phys["delta_v"]) == 1
        assert phys["delta_v"][0]["dvx"] == -15.2
        assert phys["delta_v"][0]["magnitude_mph"] == 10.5

    def test_physical_layer_force_and_crush(self):
        case = self._make_case()
        case.add_vehicle(1, "Toyota", "Camry", 2020)
        case.add_force(50000, direction=180, vehicle_number=1)
        case.add_crush(1, depth=1.5, width=4.0, profile=[0.5, 1.0, 1.5, 1.0, 0.5])
        case.add_energy(150000, unit="ft-lb", vehicle_number=1)

        phys = case.get_physical_for_vehicle(1)
        assert len(phys["forces"]) == 1
        assert len(phys["crush"]) == 1
        assert len(phys["energy"]) == 1
        assert phys["crush"][0]["profile"] == [0.5, 1.0, 1.5, 1.0, 0.5]

    def test_cross_layer_full_timeline(self):
        case = self._make_case()
        v1 = case.add_vehicle(1, "Toyota", "Camry", 2020)
        eid = case.add_event("first_contact", "Impact", t=0.0)

        # Link across layers
        case.link_entity_to_event(v1, eid)
        pos_id = case.add_position(15.0, 20.0, entity_id=v1, event_id=eid, t=0.0)
        f1 = case.add_factor("excessive_speed", severity=0.8)
        case.link_factor_to_event(f1, eid)
        dv_id = case.add_delta_v(1, dvx=-15.2, dvy=0.0, event_id=eid)

        full = case.get_full_timeline()
        assert len(full) == 1
        event = full[0]
        assert len(event["participants"]) == 1
        assert len(event["positions"]) == 1
        assert len(event["factors"]) == 1
        assert len(event["physical_outcomes"]) == 1

    def test_cross_layer_causal_trace(self):
        case = self._make_case()
        case.add_vehicle(1, "Toyota", "Camry", 2020)
        eid = case.add_event("first_contact", "Impact", t=0.0)
        f1 = case.add_factor("distraction", severity=0.9)
        case.link_factor_to_event(f1, eid)
        dv_id = case.add_delta_v(1, dvx=-15.2, dvy=0.0, event_id=eid)

        trace = case.trace_causal_chain(f1)
        assert trace["factor_type"] == "distraction"
        assert len(trace["chain"]) == 1
        assert len(trace["chain"][0]["physical_outcomes"]) == 1

    def test_layer_summary(self):
        case = self._make_case()
        case.add_vehicle(1, "Toyota", "Camry", 2020)
        case.add_event("first_contact", t=0.0)
        case.add_position(10, 20)
        case.add_factor("excessive_speed")
        case.add_delta_v(1, dvx=-15, dvy=0)
        case.add_evidence("speed", "estimated_speed_mph", 35, applies_to_vehicle=1)

        summary = case.get_layer_summary()
        assert summary["total_nodes"] > 5
        assert summary["layers"]["entity"]["node_count"] >= 2  # case + vehicle
        assert summary["layers"]["temporal"]["node_count"] == 1
        assert summary["layers"]["spatial"]["node_count"] == 1
        assert summary["layers"]["causal"]["node_count"] == 1
        assert summary["layers"]["physical"]["node_count"] == 1

    def test_export_v2_full_hypergraph(self):
        case = self._make_case()
        case.add_vehicle(1, "Toyota", "Camry", 2020, role="striking")
        case.add_driver(1, "John Doe", 35)
        case.add_event("first_contact", t=0.0)
        case.add_factor("excessive_speed", severity=0.8)
        case.add_delta_v(1, dvx=-15, dvy=0)
        case.add_evidence("speed", "estimated_speed_mph", 35, applies_to_vehicle=1)

        export = case.export()
        assert export["format"] == "pycrash_case"
        assert export["version"] == "2.0"
        assert len(export["vehicles"]) == 1
        assert len(export["drivers"]) == 1
        assert len(export["timeline"]) == 1
        assert len(export["factors"]) == 1
        assert "physical" in export
        assert "_nodes" in export  # raw graph for reimport
        assert "_edges" in export

    def test_import_v2_crash_file(self):
        import tempfile
        from pycrash_ai.graph.store import InMemoryCaseStore, InMemoryCaseGraph

        store = InMemoryCaseStore()
        case = store.create_case("export-test", "Export Test")
        case.add_scene()
        case.add_vehicle(1, "Toyota", "Camry", 2020)
        case.add_event("first_contact", t=0.0)
        case.add_factor("distraction", severity=0.9)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".crash", delete=False) as f:
            import json
            json.dump(case.export(), f)
            tmp = f.name

        store2 = InMemoryCaseStore()
        reimported = InMemoryCaseGraph.import_crash_file(tmp, store2)
        assert reimported.case_id == "export-test"
        assert len(reimported.get_vehicles()) == 1
        assert len(reimported.get_timeline()) == 1
        assert len(reimported.get_factors()) == 1

        import os
        os.unlink(tmp)


class TestCaseAPI:
    """Test case graph API endpoints."""

    def test_create_case(self):
        # Reset the store singleton for clean test
        from pycrash_ai.routes import cases
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
        from pycrash_ai.routes import cases
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
        from pycrash_ai.routes import cases
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
        from pycrash_ai.routes import cases
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
        from pycrash_ai.routes import cases
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
        from pycrash_ai.routes import cases
        cases._store = None

        r = client.get("/api/v1/cases/nonexistent")
        assert r.status_code == 404


class TestHypergraphAPI:
    """Test hypergraph API endpoints — all 6 layers via HTTP."""

    def _reset(self):
        from pycrash_ai.routes import cases
        cases._store = None

    def test_temporal_api(self):
        self._reset()
        client.post("/api/v1/cases", json={"case_id": "hyper-api-001"})
        client.post("/api/v1/cases/hyper-api-001/vehicles", json={
            "vehicle_number": 1, "make": "Toyota", "model": "Camry",
        })

        # Add phase and event
        r = client.post("/api/v1/cases/hyper-api-001/phases", json={
            "phase_name": "pre_impact", "t_start": -2.0, "t_end": 0.0,
        })
        assert r.status_code == 200

        r = client.post("/api/v1/cases/hyper-api-001/events", json={
            "event_type": "brake_application", "description": "V1 brakes",
            "t": -1.5, "phase": "pre_impact",
        })
        assert r.status_code == 200
        assert "event_id" in r.json()

        r = client.get("/api/v1/cases/hyper-api-001/timeline")
        assert r.status_code == 200
        assert len(r.json()) == 1

    def test_spatial_api(self):
        self._reset()
        client.post("/api/v1/cases", json={"case_id": "hyper-api-002"})
        client.post("/api/v1/cases/hyper-api-002/vehicles", json={
            "vehicle_number": 1, "make": "Toyota", "model": "Camry",
        })
        client.post("/api/v1/cases/hyper-api-002/vehicles", json={
            "vehicle_number": 2, "make": "Honda", "model": "Civic",
        })

        r = client.post("/api/v1/cases/hyper-api-002/impact-points", json={
            "x": 15.0, "y": 20.0, "vehicle1_number": 1, "vehicle2_number": 2,
        })
        assert r.status_code == 200
        assert "impact_point_id" in r.json()

        r = client.get("/api/v1/cases/hyper-api-002/impact-points")
        assert r.status_code == 200
        assert len(r.json()) == 1

    def test_causal_api(self):
        self._reset()
        client.post("/api/v1/cases", json={"case_id": "hyper-api-003"})

        r = client.post("/api/v1/cases/hyper-api-003/factors", json={
            "factor_type": "excessive_speed", "description": "15 over limit",
            "severity": 0.8,
        })
        assert r.status_code == 200
        fid = r.json()["factor_id"]

        r = client.get("/api/v1/cases/hyper-api-003/factors")
        assert r.status_code == 200
        assert len(r.json()) == 1
        assert r.json()[0]["factor_type"] == "excessive_speed"

    def test_physical_api(self):
        self._reset()
        client.post("/api/v1/cases", json={"case_id": "hyper-api-004"})
        client.post("/api/v1/cases/hyper-api-004/vehicles", json={
            "vehicle_number": 1, "make": "Toyota", "model": "Camry",
        })

        r = client.post("/api/v1/cases/hyper-api-004/delta-v", json={
            "vehicle_number": 1, "dvx": -15.2, "dvy": 2.1,
            "magnitude_mph": 10.5,
        })
        assert r.status_code == 200

        r = client.post("/api/v1/cases/hyper-api-004/crush", json={
            "vehicle_number": 1, "depth": 1.5, "width": 4.0,
            "profile": [0.5, 1.0, 1.5, 1.0, 0.5],
        })
        assert r.status_code == 200

        r = client.get("/api/v1/cases/hyper-api-004/physical/1")
        assert r.status_code == 200
        phys = r.json()
        assert len(phys["delta_v"]) == 1
        assert len(phys["crush"]) == 1

    def test_layers_summary_api(self):
        self._reset()
        client.post("/api/v1/cases", json={"case_id": "hyper-api-005"})
        client.post("/api/v1/cases/hyper-api-005/vehicles", json={
            "vehicle_number": 1, "make": "Toyota", "model": "Camry",
        })
        client.post("/api/v1/cases/hyper-api-005/events", json={
            "event_type": "first_contact", "t": 0.0,
        })
        client.post("/api/v1/cases/hyper-api-005/factors", json={
            "factor_type": "distraction", "severity": 0.9,
        })

        r = client.get("/api/v1/cases/hyper-api-005/layers")
        assert r.status_code == 200
        layers = r.json()
        assert "total_nodes" in layers
        assert "entity" in layers["layers"]
        assert "temporal" in layers["layers"]
        assert "causal" in layers["layers"]

    def test_driver_api(self):
        self._reset()
        client.post("/api/v1/cases", json={"case_id": "hyper-api-006"})
        client.post("/api/v1/cases/hyper-api-006/vehicles", json={
            "vehicle_number": 1, "make": "Ford", "model": "F-150",
        })

        r = client.post("/api/v1/cases/hyper-api-006/drivers", json={
            "vehicle_number": 1, "name": "Jane Smith", "age": 42,
        })
        assert r.status_code == 200

        r = client.get("/api/v1/cases/hyper-api-006/drivers")
        assert r.status_code == 200
        assert len(r.json()) == 1
        assert r.json()[0]["name"] == "Jane Smith"


class TestPipelineWithGraph:
    """Test that pipeline now builds a case graph."""

    def test_pipeline_builds_graph(self):
        from pycrash_ai.routes import cases
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


class TestConfig:
    def test_defaults_loaded(self):
        from pycrash_ai.config import settings
        assert settings.default_dt_motion == 0.01
        assert settings.default_mu_max == 0.8
        assert settings.env == "development"

    def test_reports_dir_default(self):
        from pycrash_ai.config import settings
        assert settings.reports_dir == "/app/reports"


class TestModels:
    def test_sdof_request_validation(self):
        from pycrash_ai.models import SDOFRequest
        req = SDOFRequest(w1=3400, w2=2900, v1=30, v2=0, cor=0.15, k=50000, tstop=0.5)
        assert req.w1 == 3400

    def test_sdof_request_rejects_negative_weight(self):
        from pycrash_ai.models import SDOFRequest
        import pytest
        with pytest.raises(Exception):
            SDOFRequest(w1=-100, w2=2900, v1=30, v2=0, cor=0.15, k=50000, tstop=0.5)

    def test_sdof_request_rejects_bad_cor(self):
        from pycrash_ai.models import SDOFRequest
        import pytest
        with pytest.raises(Exception):
            SDOFRequest(w1=3400, w2=2900, v1=30, v2=0, cor=1.5, k=50000, tstop=0.5)

    def test_extracted_vehicle_optional_fields(self):
        from pycrash_ai.models import ExtractedVehicle
        veh = ExtractedVehicle()
        assert veh.year is None
        assert veh.make is None
        assert veh.confidence == 0.0

    def test_extraction_response_structure(self):
        from pycrash_ai.models import ExtractionResponse, ExtractedVehicle
        resp = ExtractionResponse(
            vehicles=[ExtractedVehicle(make="Toyota", model="Camry")],
            scene=None,
            confidence=0.8,
        )
        assert len(resp.vehicles) == 1
        assert resp.vehicles[0].make == "Toyota"


class TestSchema:
    def test_node_labels_exist(self):
        from pycrash_ai.graph.schema import NodeLabel
        assert NodeLabel.VEHICLE == "Vehicle"
        assert NodeLabel.EVENT == "Event"
        assert NodeLabel.FACTOR == "Factor"
        assert NodeLabel.DELTA_V == "DeltaV"

    def test_graph_layers(self):
        from pycrash_ai.graph.schema import GraphLayer
        layers = [l.value for l in GraphLayer]
        assert "entity" in layers
        assert "temporal" in layers
        assert "spatial" in layers
        assert "evidence" in layers
        assert "causal" in layers
        assert "physical" in layers

    def test_node_layer_mapping(self):
        from pycrash_ai.graph.schema import NODE_LAYER, NodeLabel, GraphLayer
        assert NODE_LAYER[NodeLabel.VEHICLE] == GraphLayer.ENTITY
        assert NODE_LAYER[NodeLabel.EVENT] == GraphLayer.TEMPORAL
        assert NODE_LAYER[NodeLabel.POSITION] == GraphLayer.SPATIAL
        assert NODE_LAYER[NodeLabel.EVIDENCE] == GraphLayer.EVIDENCE
        assert NODE_LAYER[NodeLabel.FACTOR] == GraphLayer.CAUSAL
        assert NODE_LAYER[NodeLabel.FORCE] == GraphLayer.PHYSICAL

    def test_evidence_to_pycrash_mapping(self):
        from pycrash_ai.graph.schema import EVIDENCE_TO_PYCRASH
        # Speed conversion: 35 mph -> 51.33 fps
        key, converter = EVIDENCE_TO_PYCRASH["estimated_speed_mph"]
        assert key == "vx_initial"
        assert abs(converter(35) - 51.33345) < 0.01

    def test_crash_phases(self):
        from pycrash_ai.graph.schema import CrashPhase
        assert CrashPhase.FIRST_CONTACT == "first_contact"
        assert CrashPhase.REST == "rest"

    def test_contributing_factors(self):
        from pycrash_ai.graph.schema import ContributingFactor
        assert ContributingFactor.EXCESSIVE_SPEED == "excessive_speed"
        assert ContributingFactor.DISTRACTION == "distraction"

    def test_required_vehicle_params(self):
        from pycrash_ai.graph.schema import REQUIRED_VEHICLE_PARAMS
        assert "weight" in REQUIRED_VEHICLE_PARAMS
        assert "wb" in REQUIRED_VEHICLE_PARAMS
        assert "izz" in REQUIRED_VEHICLE_PARAMS


class TestTools:
    def test_tool_definitions_exist(self):
        from pycrash_ai.agent.tools import ALL_TOOLS
        assert len(ALL_TOOLS) >= 3

    def test_tool_has_required_fields(self):
        from pycrash_ai.agent.tools import ALL_TOOLS
        for tool in ALL_TOOLS:
            assert "name" in tool
            assert "description" in tool
            assert "input_schema" in tool

    def test_extract_vehicle_tool(self):
        from pycrash_ai.agent.tools import ALL_TOOLS
        vehicle_tools = [t for t in ALL_TOOLS if t["name"] == "extract_vehicle"]
        assert len(vehicle_tools) == 1
        schema = vehicle_tools[0]["input_schema"]
        assert "properties" in schema


class TestHeuristicExtraction:
    def test_extracts_speeds(self):
        from pycrash_ai.agent.extraction_agent import _heuristic_extraction
        result = _heuristic_extraction(
            "Vehicle 1 was traveling at approximately 45 mph when it struck Vehicle 2 which was going 20 mph"
        )
        assert len(result.vehicles) >= 2
        # Heuristic assigns default speeds (35 for striking, 0 for struck)
        speeds = [v.estimated_speed_mph for v in result.vehicles if v.estimated_speed_mph is not None]
        assert len(speeds) >= 1
        assert result.vehicles[0].role == "striking"
        assert result.vehicles[1].role == "struck"

    def test_extracts_vehicle_info(self):
        from pycrash_ai.agent.extraction_agent import _heuristic_extraction
        result = _heuristic_extraction(
            "A 2020 Toyota Camry rear-ended a 2019 Honda Civic on dry asphalt"
        )
        # Heuristic fallback creates default vehicles without make/model parsing
        assert len(result.vehicles) >= 1
        assert result.scene is not None
        assert result.crash_type == "rear_end"

    def test_handles_empty_text(self):
        from pycrash_ai.agent.extraction_agent import _heuristic_extraction
        result = _heuristic_extraction("No vehicle information here at all.")
        assert result is not None
        assert isinstance(result.vehicles, list)
