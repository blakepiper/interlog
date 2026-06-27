"""Event ↔ video time alignment.

The single, tested source of truth for mapping an interaction timestamp onto a
screen recording: ``video_time = event_time + offset``. The recorder computes the
offset and writes it to ``metadata.json``; the JS viewer mirrors
``video_time_for_event`` — keep the two in step.

Both ``mono_start`` (the logger's t=0) and ``video_first_frame_time`` (when the
recorder's first frame landed) come from the same ``time.monotonic()`` clock, so
the offset arithmetic is exact and drift-free. The residual alignment error is
purely physical (see ``frame_quantization_error``).
"""


def event_offset(mono_start, video_first_frame_time):
    """Seconds to add to an event timestamp to reach video time.

    An event at monotonic time ``T`` has session time ``T - mono_start`` and
    video time ``T - video_first_frame_time``; adding this offset recovers the
    latter (the ``mono_start`` terms cancel).
    """
    return mono_start - video_first_frame_time


def video_time_for_event(event_time, offset):
    """Map a session-relative event time onto the recording's clock.

    ``offset`` is the value from :func:`event_offset` (persisted as
    ``video_start_offset``). Callers seeking a real video element clamp negative
    results to 0; the raw value is returned here.
    """
    return event_time + offset


def frame_quantization_error(fps):
    """Worst-case alignment error from frame quantization alone, in seconds.

    The offset arithmetic is exact, but a recording only presents a new frame
    every ``1 / fps`` seconds, so an event can fall up to *half a frame* from the
    nearest captured frame. At 15 fps that is ~33 ms; at 30 fps ~17 ms.

    This is a floor, not the whole story: ``video_first_frame_time`` is recorded
    when ffmpeg *reports* its first frame over the progress pipe, which can lag
    the true first frame by a small, systematic amount. The viewer exposes a
    manual nudge control to absorb that residual, so quantization is the limit of
    the *automatic* alignment once first-frame latency is nudged out.
    """
    if fps <= 0:
        raise ValueError("fps must be positive")
    return 0.5 / fps
