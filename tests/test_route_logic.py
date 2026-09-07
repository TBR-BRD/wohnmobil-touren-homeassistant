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

    def test_resolve_from_absolute_passthrough(self):
        self.assertEqual(
            "2026-07-21T00:00:00Z", route.resolve_from("2026-07-21T00:00:00Z")
        )

    def test_resolve_from_relative_is_in_the_past(self):
        for value in ("-200d", "200d", "4w", "6m"):
            resolved = datetime.fromisoformat(route.resolve_from(value).replace("Z", "+00:00"))
            self.assertLess(resolved, datetime.now(timezone.utc))
        # 200 days ago is clearly earlier than 4 weeks ago
        self.assertLess(
            route.resolve_from("200d"), route.resolve_from("4w")
        )

    def test_explain_diagnostics_report_rejected_stays(self):
        points = [
            point(0, 0.0, 0.0),
            point(1, 0.0, 0.0),
            # only a 1 h stay here -> rejected, needs 3 h
            point(2, 0.30, 0.0),
            point(4, 0.31, 0.0),
            point(6, 0.0, 0.0),
            point(7, 0.0, 0.0),
            point(8, 0.0, 0.0),
            point(9, 0.0, 0.0),
        ]
        diagnostics: dict = {}
        tours, stays = route.split_tours(
            points,
            home_lat=0.0,
            home_lon=0.0,
            home_radius_km=20.0,
            return_confirm_hours=3.0,
            home_stay_radius_km=1.0,
            diagnostics=diagnostics,
        )

        candidates = diagnostics["stay_candidates"]
        self.assertTrue(candidates)
        confirmed = [c for c in candidates if c["confirmed"]]
        rejected = [c for c in candidates if not c["confirmed"]]
        self.assertEqual(len(confirmed), len(stays))
        self.assertTrue(any("need 3.00 h" in c["reason"] for c in rejected))
        for entry in candidates:
            self.assertIn(entry["window_ended_because"], {
                "end_of_data", "left_home_radius", "moved_from_anchor",
            })

    def test_build_result_diagnostics_do_not_change_default_output(self):
        points = [
            point(0, 0.0, 0.0),
            point(1, 0.0, 0.0),
            point(2, 0.0, 0.0),
            point(3, 0.0, 0.0),
            point(4, 0.30, 0.0),
            point(5, 0.0, 0.0),
            point(6, 0.0, 0.0),
            point(7, 0.0, 0.0),
        ]
        base_args = dict(
            home_lat=0.0,
            home_lon=0.0,
            home_radius_km=20.0,
            return_confirm_hours=3.0,
            home_stay_radius_km=1.0,
        )
        tours_plain, _ = route.split_tours(points, **base_args)
        tours_diag, _ = route.split_tours(points, diagnostics={}, **base_args)
        self.assertEqual(
            [len(t["points"]) for t in tours_plain],
            [len(t["points"]) for t in tours_diag],
        )


if __name__ == "__main__":
    unittest.main()
