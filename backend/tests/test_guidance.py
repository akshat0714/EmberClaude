"""GuidanceBrain guardrails: no unsafe language, always defers to officials."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

BANNED_PHRASES = [
    "guaranteed safe", "guarantee", "exact safe route", "ignore official",
    "ignore the officials", "definitely save", "perfectly safe", "100% safe",
]

PROBES = [
    "Where do I go?",
    "I can't see ahead. It's bright orange.",
    "I missed the turn",
    "The road looks blocked",
    "Repeat instruction",
    "Am I safe yet?",
    "Should I keep going?",
    "What if I missed the turn?",
    "status",
    "tell me something",
]


def test_guidance_never_promises_guaranteed_safety():
    for probe in PROBES:
        r = client.post("/guidance/respond", json={"text": probe, "minute": 10.0})
        assert r.status_code == 200, probe
        body = r.json()
        for field in ("transcriptText", "speechText"):
            low = body[field].lower()
            for banned in BANNED_PHRASES:
                assert banned not in low, f"{probe!r} produced banned phrase {banned!r}"


def test_every_response_defers_to_official_guidance():
    for probe in PROBES:
        body = client.post("/guidance/respond", json={"text": probe, "minute": 10.0}).json()
        assert "official" in body["transcriptText"].lower(), (
            f"{probe!r} response must reference official guidance")
        assert "official" in body["safetyReminder"].lower()


def test_intents_detected():
    cases = {
        "Where do I go?": "where_do_i_go",
        "I can't see ahead, it's bright orange": "visibility_lost",
        "I missed the turn": "missed_turn",
        "the road looks blocked": "road_blocked",
        "am I safe yet?": "am_i_safe",
        "what if I missed the turn?": "hypothetical_missed_turn",
        "should I keep going?": "keep_going",
    }
    for text, expected in cases.items():
        body = client.post("/guidance/respond", json={"text": text, "minute": 5.0}).json()
        assert body["intent"] == expected, f"{text!r} -> {body['intent']} != {expected}"


def test_guidance_only_reads_engine_maneuvers():
    """The brain must quote route-engine instructions, not invent streets."""
    r = client.post("/guidance/respond", json={"text": "Where do I go?", "minute": 10.0})
    body = r.json()
    rec = body["recommendation"]
    assert rec is not None
    best = next(c for c in rec["candidates"] if c["routeId"] == rec["recommendedRouteId"])
    known_roads = {m["roadName"] for m in best["maneuvers"]} | {"the route", "current road"}
    # Every capitalized road-like phrase the brain spoke must come from the engine.
    spoken = body["transcriptText"]
    for road in ("Boulevard", "Drive", "Road", "Highway", "Avenue"):
        for word in spoken.split("."):
            if road in word:
                assert any(k in word for k in known_roads), (
                    f"spoken road segment {word!r} not backed by engine maneuvers")
