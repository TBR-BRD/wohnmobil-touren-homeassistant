from __future__ import annotations

import importlib.util
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "wohnmobil_route.py"
spec = importlib.util.spec_from_file_location("wohnmobil_route", MODULE_PATH)
route = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(route)


def point(hours: float, lat: float, lon: float):
    timestamp = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(hours=hours)
    return {
        "latitude": lat,
        "longitude": lon,
        "fixTime": timestamp.isoformat(),
    }


class TourLogicTest(unittest.TestCase):
    def test_closed_tour_keeps_home_zone_start_and_end(self):
        # Four hours stationary at home -> confirmed home stay.
        points = [
            point(0, 0.0, 0.0),
            point(1, 0.0, 0.0),
            point(2, 0.0, 0.0),
            point(3, 0.0, 0.0),
            # Departure still inside the broad 20 km radius.
            point(4, 0.02, 0.0),
            # Clearly outside the broad radius.
            point(5, 0.30, 0.0),
            # Return inside broad radius, then stationary home stay.
            point(6, 0.02, 0.0),
            point(7, 0.0, 0.0),
            point(8, 0.0, 0.0),
            point(9, 0.0, 0.0),
            point(10, 0.0, 0.0),
        ]

        tours, stays = route.split_tours(
            points,
            home_lat=0.0,
            home_lon=0.0,
            home_radius_km=20.0,
            return_confirm_hours=3.0,
            home_stay_radius_km=1.0,
        )

        self.assertEqual(2, len(stays))
        self.assertEqual(1, len(tours))
        tour_points = tours[0]["points"]
        self.assertEqual(points[3], tour_points[0])
        self.assertEqual(points[7], tour_points[-1])
        self.assertFalse(tours[0]["active"])
        self.assertFalse(tours[0]["partial_start"])

    def test_no_confirmed_return_is_active(self):
        points = [
            point(0, 0.0, 0.0),
            point(1, 0.0, 0.0),
            point(2, 0.0, 0.0),
            point(3, 0.0, 0.0),
            point(4, 0.02, 0.0),
            point(5, 0.30, 0.0),
        ]
        tours, _ = route.split_tours(
            points,
            home_lat=0.0,
            home_lon=0.0,
            home_radius_km=20.0,
            return_confirm_hours=3.0,
            home_stay_radius_km=1.0,
        )
        self.assertEqual(1, len(tours))
        self.assertTrue(tours[0]["active"])

    def test_haversine_zero(self):
        self.assertAlmostEqual(0.0, route.haversine_km(1.0, 2.0, 1.0, 2.0))


if __name__ == "__main__":
    unittest.main()
