SmartkingLot Test README
========================

Unit Tests
----------

Unit test code is located in:

- /tests/test_unit_processing.py

These tests check small helper functions from /api/server.py in isolation:

- iou()
- nms()
- match_detections_to_spots()
- filter_by_size()

Run the unit tests from the project root:

  pytest tests/test_unit_processing.py


Integration Tests
-----------------

Integration test code is located in:

- /tests/conftest.py
- /tests/test_occupancy.py

These tests check the combined detector, API, database, and sample image
pipeline. They load images from /fake-stream, run the real detector, post to
POST /api/snapshot, and verify the saved state from GET /api/state.

Run the integration tests from the project root:

  pytest tests/test_occupancy.py


Run All Tests
-------------

Run all unit and integration tests from the project root:

  pytest tests/

For detailed output:

  pytest tests/ -v -s


Requirements
------------

Install dependencies before running tests:

  pip install -r requirements.txt

The integration tests require the trained model file:

  /models/best_320x12n.pt

The fake stream server does not need to be running for the tests.
