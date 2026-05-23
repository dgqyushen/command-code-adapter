from cc_adapter.core.log_buffer import append, get_entries, buffer_size, clear


def test_append_and_retrieve():
    clear()
    append({"timestamp": "2026-05-23T14:30:45", "level": "INFO", "event": "test.event", "msg": "hello"})
    append({"timestamp": "2026-05-23T14:30:46", "level": "INFO", "event": "test.error", "msg": "fail"})

    all_entries = get_entries(level="INFO")
    assert len(all_entries) == 2
    # Newest first (reversed)
    assert all_entries[0]["event"] == "test.error"
    assert all_entries[1]["event"] == "test.event"


def test_level_filter():
    clear()
    append({"timestamp": "2026-05-23T14:30:45", "level": "DEBUG", "event": "debug.event"})
    append({"timestamp": "2026-05-23T14:30:46", "level": "INFO", "event": "info.event"})
    append({"timestamp": "2026-05-23T14:30:47", "level": "WARNING", "event": "warn.event"})
    append({"timestamp": "2026-05-23T14:30:48", "level": "ERROR", "event": "error.event"})

    assert len(get_entries(level="INFO")) == 1
    assert get_entries(level="INFO")[0]["event"] == "info.event"
    assert len(get_entries(level="WARNING")) == 1
    assert get_entries(level="WARNING")[0]["event"] == "warn.event"
    assert len(get_entries(level="ERROR")) == 1
    assert get_entries(level="ERROR")[0]["event"] == "error.event"
    assert len(get_entries(level="DEBUG")) == 1
    assert get_entries(level="DEBUG")[0]["event"] == "debug.event"


def test_search():
    clear()
    append({"timestamp": "2026-05-23T14:30:45", "level": "INFO", "event": "http.done", "method": "POST"})
    append({"timestamp": "2026-05-23T14:30:46", "level": "INFO", "event": "auth.failed", "reason": "bad token"})
    append({"timestamp": "2026-05-23T14:30:47", "level": "INFO", "event": "http.done", "method": "GET"})

    results = get_entries(search="auth")
    assert len(results) == 1
    assert results[0]["event"] == "auth.failed"

    results = get_entries(search="http")
    assert len(results) == 2

    results = get_entries(search="nonexistent")
    assert len(results) == 0


def test_search_case_insensitive():
    clear()
    append({"timestamp": "2026-05-23T14:30:45", "level": "INFO", "event": "Http.Done", "method": "POST"})

    results = get_entries(search="http")
    assert len(results) == 1


def test_limit():
    clear()
    for i in range(10):
        append({"timestamp": f"2026-05-23T14:30:{i:02d}", "level": "INFO", "event": f"event.{i}"})

    results = get_entries(limit=3)
    assert len(results) == 3
    # Newest first
    assert results[0]["event"] == "event.9"


def test_empty_buffer():
    clear()
    results = get_entries()
    assert len(results) == 0
    assert buffer_size() == 0


def test_buffer_maxlen():
    clear()
    # Fill beyond default 1000
    for i in range(1500):
        append({"level": "INFO", "event": f"event.{i}"})

    assert buffer_size() == 1000
    # Oldest entries dropped — verify newest are present
    results = get_entries(limit=1)
    assert results[0]["event"] == "event.1499"


def test_clear():
    clear()
    append({"level": "INFO", "event": "test"})
    assert buffer_size() == 1
    clear()
    assert buffer_size() == 0
