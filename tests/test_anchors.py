from screenjarvis.compiler import anchors as A

MON = {"left": 0, "top": 0, "width": 1440, "height": 900}


def w(word, start, end):
    return {"word": word, "start": start, "end": end}


def frame(t, reason="tick", path="raw/frames/x.jpg"):
    return {"t": t, "type": "frame", "path": path, "mon": dict(MON), "w": 1440, "h": 900, "reason": reason}


def test_trigger_matching_normalizes_case_and_punctuation():
    words = [w("Look", 1.0, 1.2), w("at", 1.2, 1.4), w("this,", 1.4, 1.6), w("please", 1.6, 1.8)]
    assert A.find_trigger_spans(words, ["look at this"]) == [(0, 2, "look at this")]


def test_longest_phrase_wins_at_same_position():
    words = [w("this", 1.0, 1.2), w("one", 1.2, 1.4), w("here", 1.4, 1.6)]
    spans = A.find_trigger_spans(words, ["this one", "this one here"])
    assert spans == [(0, 2, "this one here")]


def test_no_false_fire_on_decoys():
    words = [w(token, i * 0.3, i * 0.3 + 0.25) for i, token in
             enumerate("we shipped this last week and this is why it works".split())]
    assert A.find_trigger_spans(words, A.DEFAULT_TRIGGER_PHRASES) == []


def test_cursor_interpolation_between_samples():
    samples = [{"t": 1.0, "x": 100, "y": 200}, {"t": 2.0, "x": 200, "y": 400}]
    assert A.cursor_at(samples, 1.5) == (150, 300)
    assert A.cursor_at(samples, 0.0) == (100, 200)   # clamp before first
    assert A.cursor_at(samples, 5.0) == (200, 400)   # clamp after last


def test_cursor_snaps_across_log_gaps():
    samples = [{"t": 1.0, "x": 100, "y": 100}, {"t": 5.0, "x": 900, "y": 900}]
    assert A.cursor_at(samples, 1.4) == (100, 100)  # gap > 1.5s: nearest, not lerp


def test_click_anchors_and_merge_prefer_clicked():
    transcript = {"words": [
        w("look", 1.0, 1.2), w("at", 1.2, 1.4), w("this", 1.4, 1.6),
        w("right", 2.2, 2.4), w("here", 2.4, 2.6),
    ]}
    events = {
        "cursor": [{"t": 0.0, "x": 10, "y": 10}, {"t": 5.0, "x": 10, "y": 10}],
        "clicks": [{"t": 2.5, "x": 99, "y": 88, "button": "left"}],
        "frames": [frame(1.5), frame(2.55, reason="click")],
    }
    result = A.detect(transcript, events, ["look at this", "right here"])
    # both triggers fall inside one merge window; the clicked one wins
    assert len(result) == 1
    assert result[0].clicked
    assert result[0].phrase == "right here"
    assert result[0].cursor == (99, 88)
    assert result[0].frame["reason"] == "click"


def test_far_apart_anchors_are_kept_separate():
    transcript = {"words": [
        w("look", 1.0, 1.2), w("at", 1.2, 1.4), w("this", 1.4, 1.6),
        w("right", 9.2, 9.4), w("here", 9.4, 9.6),
    ]}
    events = {
        "cursor": [{"t": 0.0, "x": 10, "y": 10}, {"t": 10.0, "x": 10, "y": 10}],
        "clicks": [],
        "frames": [frame(1.5), frame(9.5)],
    }
    result = A.detect(transcript, events, ["look at this", "right here"])
    assert [a.phrase for a in result] == ["look at this", "right here"]
