"""Event ↔ video time alignment.

The single, tested source of truth for how an interaction timestamp maps onto a
screen recording's timeline. The recorder computes an *offset* and writes it into
``metadata.json``; the viewer applies ``video_time = event_time + offset`` to
seek the recording to a given moment. The JS viewer mirrors
``video_time_for_event`` — keep the two in step.

Timing model
------------
Both the logger and the screen recorder read the same monotonic clock
(``time.monotonic()``):

* ``mono_start`` — the logger's t=0 (the instant ``start()`` begins capturing).
* ``video_first_frame_time`` — the monotonic time the recorder's first frame
  landed (returned by ``ScreenRecorder.start_and_wait_until_live``).

Because both readings come from the *same* monotonic clock, their difference is
free of drift and immune to wall-clock adjustments (NTP, DST, manual changes)
during a session. The offset arithmetic below is therefore exact; the residual
alignment error is purely physical (see ``frame_quantization_error``).
"""


def event_offset(mono_start, video_first_frame_time):
    """Seconds to add to an event timestamp to reach video time.

    ``event_offset`` inverts the two clocks' relationship: an event captured at
    absolute monotonic time ``T`` has session time ``T - mono_start`` and should
    map to video time ``T - video_first_frame_time``. Adding this offset to the
    session time recovers exactly that (the ``mono_start`` terms cancel).
    """
    return mono_start - video_first_frame_time


def video_time_for_event(event_time, offset):
    """Map a session-relative event time onto the recording's clock.

    ``offset`` is the value from :func:`event_offset` (also persisted as
    ``video_start_offset`` in session metadata). Negative results are clamped to
    0 by callers that seek a real video element; the raw value is returned here.
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
