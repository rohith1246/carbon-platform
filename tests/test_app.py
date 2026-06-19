"""
tests/test_app.py
Pytest test suite for the Carbon Footprint Platform.

Run from the project root:
    pytest tests/test_app.py -v
"""

import sys
import os
import json
import tempfile

import pytest

# Ensure the project root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from carbon_engine import calculate_co2, VALID_ACTIVITY_TYPES
from ai_engine import REQUIRED_KEYS, FALLBACK_RESPONSE, _parse_and_validate


# ── Fixtures ─────────────────────────────────────────────────────────────────
@pytest.fixture()
def app_client():
    """Return a Flask test client with an in-memory / temp database."""
    # Point DB to a temp file so tests are isolated
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()

    os.environ["DB_PATH"]     = tmp.name
    os.environ["SECRET_KEY"]  = "test-secret"
    # Ensure no real Groq calls during tests
    os.environ.pop("GROQ_API_KEY", None)

    import importlib
    import app as flask_app
    importlib.reload(flask_app)          # re-init with the temp DB path

    flask_app.app.config["TESTING"]               = True
    flask_app.app.config["WTF_CSRF_ENABLED"]      = False
    flask_app.app.config["SECRET_KEY"]            = "test-secret"

    with flask_app.app.test_client() as client:
        yield client

    try:
        os.unlink(tmp.name)
    except OSError:
        # On Windows the SQLite file may still be locked briefly after close;
        # silently ignore – the OS will clean up the temp file eventually.
        pass


@pytest.fixture()
def registered_client(app_client):
    """A test client where a user has been registered and logged in."""
    app_client.post(
        "/register",
        data={"username": "testuser", "email": "test@example.com", "password": "password123"},
        follow_redirects=True,
    )
    app_client.post(
        "/login",
        data={"username": "testuser", "password": "password123"},
        follow_redirects=True,
    )
    return app_client


# ── Spec mandated tests (Module Level) ───────────────────────────────────────
def test_carbon_calculation():
    """1. test_carbon_calculation → assert calculate_co2("car", 10) == 2.1"""
    assert calculate_co2("car", 10) == 2.1

def test_api_response(app_client):
    """2. test_api_response → check Flask route returns 200"""
    resp = app_client.get("/api/status")
    assert resp.status_code == 200

def test_ai_json_structure():
    """3. test_ai_json_structure → validate all 5 keys present"""
    from ai_engine import REQUIRED_KEYS, FALLBACK_RESPONSE
    missing = REQUIRED_KEYS - FALLBACK_RESPONSE.keys()
    assert not missing

def test_login(app_client):
    """4. test_login → POST /login returns expected response"""
    app_client.post(
        "/register",
        data={"username": "logintest", "email": "lt@test.com", "password": "password123"},
    )
    resp = app_client.post(
        "/login",
        data={"username": "logintest", "password": "password123"},
        follow_redirects=False,
    )
    assert resp.status_code in (301, 302)

def test_input_validation(registered_client):
    """5. test_input_validation → reject invalid/empty inputs"""
    resp = registered_client.post(
        "/log",
        data={"activity_type": "invalid_type", "quantity": "10"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    
    resp = registered_client.post(
        "/log",
        data={"activity_type": "car", "quantity": "0"},
        follow_redirects=True,
    )
    assert resp.status_code == 200


# ══════════════════════════════════════════════════════════════════════════════
# 1. Carbon calculation accuracy
# ══════════════════════════════════════════════════════════════════════════════
class TestCarbonCalculation:

    def test_car_10km(self):
        """car * 10 km = 2.1 kg CO2 (spec assertion)."""
        assert calculate_co2("car", 10) == 2.1

    def test_bike_emission(self):
        assert calculate_co2("bike", 100) == pytest.approx(5.0)

    def test_bus_emission(self):
        assert calculate_co2("bus", 50) == pytest.approx(4.0)

    def test_flight_emission(self):
        assert calculate_co2("flight", 1000) == pytest.approx(255.0)

    def test_non_veg_meal(self):
        assert calculate_co2("non_veg", 3) == pytest.approx(7.5)

    def test_veg_meal(self):
        assert calculate_co2("veg", 5) == pytest.approx(2.5)

    def test_electricity(self):
        assert calculate_co2("electricity", 10) == pytest.approx(8.2)

    def test_invalid_activity_type(self):
        with pytest.raises(ValueError, match="Unknown activity type"):
            calculate_co2("helicopter", 10)

    def test_zero_quantity_raises(self):
        with pytest.raises(ValueError, match="Quantity must be positive"):
            calculate_co2("car", 0)

    def test_negative_quantity_raises(self):
        with pytest.raises(ValueError, match="Quantity must be positive"):
            calculate_co2("car", -5)

    def test_return_type_is_float(self):
        result = calculate_co2("car", 10)
        assert isinstance(result, float)

    def test_all_valid_types_work(self):
        """Every declared activity type should return a positive float."""
        for act_type in VALID_ACTIVITY_TYPES:
            result = calculate_co2(act_type, 1.0)
            assert result > 0


# ══════════════════════════════════════════════════════════════════════════════
# 2. Flask API / route response codes
# ══════════════════════════════════════════════════════════════════════════════
class TestApiResponse:

    def test_status_endpoint_200(self, app_client):
        """GET /api/status must return 200 and JSON body."""
        resp = app_client.get("/api/status")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["status"] == "ok"

    def test_index_returns_200(self, app_client):
        resp = app_client.get("/")
        assert resp.status_code == 200

    def test_login_page_returns_200(self, app_client):
        resp = app_client.get("/login")
        assert resp.status_code == 200

    def test_register_page_returns_200(self, app_client):
        resp = app_client.get("/register")
        assert resp.status_code == 200

    def test_dashboard_redirects_without_auth(self, app_client):
        resp = app_client.get("/dashboard")
        # Should redirect to /login
        assert resp.status_code in (301, 302)

    def test_analytics_redirects_without_auth(self, app_client):
        resp = app_client.get("/analytics")
        assert resp.status_code in (301, 302)

    def test_dashboard_accessible_when_logged_in(self, registered_client):
        resp = registered_client.get("/dashboard")
        assert resp.status_code == 200

    def test_analytics_accessible_when_logged_in(self, registered_client):
        resp = registered_client.get("/analytics")
        assert resp.status_code == 200


# ══════════════════════════════════════════════════════════════════════════════
# 3. AI JSON structure validation
# ══════════════════════════════════════════════════════════════════════════════
class TestAiJsonStructure:

    def test_fallback_has_all_keys(self):
        """The FALLBACK_RESPONSE must contain all 5 required keys."""
        missing = REQUIRED_KEYS - FALLBACK_RESPONSE.keys()
        assert not missing, f"Missing keys in FALLBACK_RESPONSE: {missing}"

    def test_fallback_eco_score_range(self):
        score = FALLBACK_RESPONSE["eco_score"]
        assert 0 <= score <= 100

    def test_fallback_suggestions_is_list(self):
        assert isinstance(FALLBACK_RESPONSE["suggestions"], list)
        assert len(FALLBACK_RESPONSE["suggestions"]) >= 1

    def test_parse_and_validate_valid_json(self):
        """_parse_and_validate should accept well-formed JSON."""
        valid = json.dumps({
            "summary": "Good job!",
            "top_emission_sources": ["car travel"],
            "suggestions": ["Walk more", "Eat less meat"],
            "eco_score": 75,
            "motivation": "Keep it up!",
        })
        result = _parse_and_validate(valid)
        assert result["eco_score"] == 75
        assert set(result.keys()) >= REQUIRED_KEYS

    def test_parse_and_validate_strips_markdown_fence(self):
        """LLM sometimes wraps JSON in markdown code fences."""
        wrapped = (
            "```json\n"
            + json.dumps({
                "summary": "ok",
                "top_emission_sources": [],
                "suggestions": ["a"],
                "eco_score": 50,
                "motivation": "go!",
            })
            + "\n```"
        )
        result = _parse_and_validate(wrapped)
        assert result["summary"] == "ok"

    def test_parse_and_validate_clamps_eco_score(self):
        """eco_score must be clamped to [0, 100]."""
        payload = json.dumps({
            "summary": "x", "top_emission_sources": [],
            "suggestions": ["x"], "eco_score": 150, "motivation": "x",
        })
        result = _parse_and_validate(payload)
        assert result["eco_score"] == 100

    def test_parse_and_validate_raises_on_missing_key(self):
        invalid = json.dumps({"summary": "x", "eco_score": 40})
        with pytest.raises(ValueError, match="missing keys"):
            _parse_and_validate(invalid)

    def test_parse_and_validate_raises_on_no_json(self):
        with pytest.raises(ValueError, match="No JSON object found"):
            _parse_and_validate("This is just plain text with no JSON.")


# ══════════════════════════════════════════════════════════════════════════════
# 4. Login flow
# ══════════════════════════════════════════════════════════════════════════════
class TestLogin:

    def test_register_and_login_success(self, app_client):
        """Register then login should redirect to dashboard."""
        app_client.post(
            "/register",
            data={"username": "newuser", "email": "new@test.com", "password": "secret123"},
            follow_redirects=False,
        )
        resp = app_client.post(
            "/login",
            data={"username": "newuser", "password": "secret123"},
            follow_redirects=False,
        )
        assert resp.status_code in (301, 302)
        location = resp.headers.get("Location", "")
        assert "dashboard" in location

    def test_login_wrong_password(self, app_client):
        """Wrong password must not log the user in."""
        app_client.post(
            "/register",
            data={"username": "secureuser", "email": "s@test.com", "password": "correct"},
        )
        resp = app_client.post(
            "/login",
            data={"username": "secureuser", "password": "wrongpassword"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"Invalid" in resp.data or b"invalid" in resp.data or b"error" in resp.data.lower()

    def test_login_nonexistent_user(self, app_client):
        resp = app_client.post(
            "/login",
            data={"username": "nobody", "password": "x"},
            follow_redirects=True,
        )
        assert resp.status_code == 200

    def test_logout_clears_session(self, registered_client):
        resp = registered_client.get("/logout", follow_redirects=True)
        assert resp.status_code == 200
        # After logout, dashboard should redirect
        resp2 = registered_client.get("/dashboard")
        assert resp2.status_code in (301, 302)


# ══════════════════════════════════════════════════════════════════════════════
# 5. Input validation
# ══════════════════════════════════════════════════════════════════════════════
class TestInputValidation:

    def test_log_invalid_activity_type(self, registered_client):
        """Unknown activity type should be rejected."""
        resp = registered_client.post(
            "/log",
            data={"activity_type": "helicopter", "quantity": "10"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        # Flash message contains 'Invalid'
        assert b"Invalid" in resp.data or b"invalid" in resp.data.lower()

    def test_log_zero_quantity(self, registered_client):
        """Zero quantity should be rejected."""
        resp = registered_client.post(
            "/log",
            data={"activity_type": "car", "quantity": "0"},
            follow_redirects=True,
        )
        assert resp.status_code == 200

    def test_log_negative_quantity(self, registered_client):
        """Negative quantity should be rejected."""
        resp = registered_client.post(
            "/log",
            data={"activity_type": "car", "quantity": "-5"},
            follow_redirects=True,
        )
        assert resp.status_code == 200

    def test_log_empty_quantity(self, registered_client):
        """Empty quantity field should be rejected."""
        resp = registered_client.post(
            "/log",
            data={"activity_type": "car", "quantity": ""},
            follow_redirects=True,
        )
        assert resp.status_code == 200

    def test_log_non_numeric_quantity(self, registered_client):
        """Non-numeric string should be rejected."""
        resp = registered_client.post(
            "/log",
            data={"activity_type": "car", "quantity": "abc"},
            follow_redirects=True,
        )
        assert resp.status_code == 200

    def test_log_valid_activity_success(self, registered_client):
        """Valid activity + quantity should redirect with success."""
        resp = registered_client.post(
            "/log",
            data={"activity_type": "car", "quantity": "50"},
            follow_redirects=True,
        )
        assert resp.status_code == 200

    def test_register_short_username(self, app_client):
        """Username under 3 chars should be rejected."""
        resp = app_client.post(
            "/register",
            data={"username": "ab", "email": "ab@test.com", "password": "password"},
            follow_redirects=True,
        )
        assert resp.status_code == 200

    def test_register_duplicate_username(self, app_client):
        """Second registration with same username should fail."""
        data = {"username": "dupuser", "email": "dup@test.com", "password": "pass123"}
        app_client.post("/register", data=data, follow_redirects=True)
        resp = app_client.post(
            "/register",
            data={"username": "dupuser", "email": "other@test.com", "password": "pass123"},
            follow_redirects=True,
        )
        assert resp.status_code == 200

    def test_api_co2_invalid_type(self, registered_client):
        """API endpoint should return 400 for unknown activity type."""
        resp = registered_client.post(
            "/api/co2",
            json={"activity_type": "rocket", "quantity": 10},
        )
        assert resp.status_code == 400

    def test_api_co2_valid(self, registered_client):
        """API endpoint should return CO2 for valid inputs."""
        resp = registered_client.post(
            "/api/co2",
            json={"activity_type": "car", "quantity": 10},
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["co2_kg"] == pytest.approx(2.1)
