# SmartkingLot - Unit Tests
# Written by: Andrew Klundt, Aiden Fenstermacher
# Assisted by: Rohan Ginjupalli, Evan Biggins
# Tested by: Andrew Klundt, Aiden Fenstermacher
# Debugged by: Andrew Klundt, Aiden Fenstermacher
# Description: Tests small API processing helper functions in isolation.

import server


def make_detection(cx, cy, w=20, h=20, occupied=True, confidence=0.9):
    return {
        'cx': cx,
        'cy': cy,
        'w': w,
        'h': h,
        'occupied': occupied,
        'confidence': confidence,
    }


def test_iou_identical_boxes_is_one():
    box = make_detection(50, 50)
    assert server.iou(box, box) == 1


def test_nms_keeps_highest_confidence_box():
    high = make_detection(50, 50, confidence=0.95)
    low = make_detection(50, 50, confidence=0.50)

    result = server.nms([low, high])

    assert result == [high]


def test_match_detections_to_registered_spots():
    detections = [make_detection(102, 98, occupied=False)]
    spots = [{'id': 7, 'cx': 100, 'cy': 100}]

    result = server.match_detections_to_spots(detections, spots)

    assert result == {7: False}


def test_filter_by_size_skips_small_detection_sets():
    detections = [
        make_detection(10, 10),
        make_detection(20, 20),
        make_detection(30, 30),
    ]

    assert server.filter_by_size(detections) == detections
