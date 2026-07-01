"""Tests for interlog.sync: event <-> video alignment and error budget."""

import pytest

from interlog.sync import event_offset, frame_quantization_error, video_time_for_event


def test_event_offset_recovers_video_time():
    """Mapping an event through the offset lands it on the video clock exactly.

    An event captured at absolute monotonic time T has session time
    T - mono_start and should map to video time T - first_frame. Composing
    event_offset + video_time_for_event must recover that, with the mono_start
    terms cancelling — for any clock origins.
    """
    mono_start = 1000.0
    first_frame = 998.5            # video began 1.5 s before logging started
    offset = event_offset(mono_start, first_frame)
    assert offset == pytest.approx(1.5)

    for abs_t in (1000.0, 1002.25, 1010.0):       # absolute monotonic capture times
        event_time = abs_t - mono_start            # what the recorder stores
        expected_video_time = abs_t - first_frame  # ground truth on the video clock
        assert video_time_for_event(event_time, offset) == pytest.approx(expected_video_time)


def test_event_offset_negative_when_logging_leads_video():
    # Logger started before the first frame -> early events map before video t=0.
    offset = event_offset(1000.0, 1002.0)
    assert offset == pytest.approx(-2.0)
    assert video_time_for_event(0.5, offset) == pytest.approx(-1.5)


def test_frame_quantization_error_halves_with_fps():
    assert frame_quantization_error(15) == pytest.approx(1 / 30)
    assert frame_quantization_error(30) == pytest.approx(1 / 60)
    assert frame_quantization_error(30) < frame_quantization_error(15)


def test_frame_quantization_error_rejects_nonpositive_fps():
    with pytest.raises(ValueError):
        frame_quantization_error(0)
