import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "ghl-agent"))

from ghl_client import StubGHLClient  # noqa: E402
from models import ContactRef  # noqa: E402
from pipeline import CallCapturePipeline, format_ghl_note  # noqa: E402
from summarizer import CallSummary, StubSummarizerClient  # noqa: E402
from transcriber import StubTranscriberClient  # noqa: E402


def make_pipeline(**kwargs):
    return CallCapturePipeline(
        transcriber=StubTranscriberClient(),
        summarizer=StubSummarizerClient(),
        ghl=StubGHLClient(),
        **kwargs,
    )


def test_transcribe_produces_full_text():
    pipeline = make_pipeline()
    result = pipeline.run(
        audio_path="fake.wav",
        contact=ContactRef(email="hamsel@example.com", name="Hamsel"),
        consent_disclosed=True,
    )
    assert "Mission Villa" in result.transcript.full_text
    assert result.transcript.duration_sec > 0


def test_summary_extracts_action_items():
    pipeline = make_pipeline()
    result = pipeline.run(
        audio_path="fake.wav",
        contact=ContactRef(email="hamsel@example.com", name="Hamsel"),
        consent_disclosed=True,
    )
    assert len(result.call_summary.action_items) >= 1
    assert result.call_summary.sentiment in ("positive", "neutral", "negative")


def test_ghl_sync_creates_contact_and_note():
    pipeline = make_pipeline()
    result = pipeline.run(
        audio_path="fake.wav",
        contact=ContactRef(email="hamsel@example.com", name="Hamsel"),
        consent_disclosed=True,
    )
    assert result.ghl_synced is True
    assert result.ghl_contact_id is not None
    assert result.ghl_note_id is not None


def test_ghl_note_contains_transcript_and_summary():
    pipeline = make_pipeline()
    ghl = pipeline.ghl
    result = pipeline.run(
        audio_path="fake.wav",
        contact=ContactRef(email="hamsel@example.com", name="Hamsel"),
        consent_disclosed=True,
    )
    contact = ghl.contacts["hamsel@example.com"]
    note_body = contact["notes"][0]["body"]
    assert result.call_summary.summary in note_body
    assert "Mission Villa" in note_body
    assert "Consent disclosed" in note_body


def test_missing_consent_flags_note():
    pipeline = make_pipeline()
    ghl = pipeline.ghl
    pipeline.run(
        audio_path="fake.wav",
        contact=ContactRef(email="nocall@example.com", name="No Consent"),
        consent_disclosed=False,
    )
    contact = ghl.contacts["nocall@example.com"]
    note_body = contact["notes"][0]["body"]
    assert "NOT confirmed" in note_body


def test_sync_to_ghl_false_skips_ghl():
    pipeline = make_pipeline()
    result = pipeline.run(
        audio_path="fake.wav",
        contact=ContactRef(email="skip@example.com"),
        consent_disclosed=True,
        sync_to_ghl=False,
    )
    assert result.ghl_synced is False
    assert result.ghl_contact_id is None
    assert "skip@example.com" not in pipeline.ghl.contacts


def test_second_call_same_contact_reuses_contact():
    pipeline = make_pipeline()
    contact = ContactRef(email="repeat@example.com", name="Repeat Caller")
    r1 = pipeline.run(audio_path="a.wav", contact=contact, consent_disclosed=True)
    r2 = pipeline.run(audio_path="b.wav", contact=contact, consent_disclosed=True)
    assert r1.ghl_contact_id == r2.ghl_contact_id
    assert len(pipeline.ghl.contacts["repeat@example.com"]["notes"]) == 2


def test_stub_transcriber_records_calls():
    t = StubTranscriberClient()
    t.transcribe("call1.wav")
    t.transcribe("call2.wav")
    assert t.calls == ["call1.wav", "call2.wav"]


def test_stub_summarizer_detects_negative_sentiment():
    s = StubSummarizerClient()
    from models import Transcript
    transcript = Transcript(full_text="There's a big problem, this won't work for us.")
    summary = s.summarize(transcript)
    assert summary.sentiment == "negative"


def test_format_ghl_note_no_action_items():
    summary = CallSummary(summary="Quick check-in call.", action_items=[],
                          key_topics=[], sentiment="neutral")
    note = format_ghl_note(summary, "Hello there.", consent_disclosed=True)
    assert "(none)" in note
    assert "n/a" in note
