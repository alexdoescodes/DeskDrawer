import QtQuick
import QtTest
import "../code/format.js" as Format

TestCase {
    name: "Format"

    readonly property real hour: 3600
    readonly property real now: 1000

    function test_whole_hours() {
        compare(Format.remainingLabel(now + 18 * hour, now), "18h");
    }

    function test_rounds_down_to_the_hour() {
        compare(Format.remainingLabel(now + 4.9 * hour, now), "4h");
    }

    function test_under_an_hour_shows_minutes() {
        compare(Format.remainingLabel(now + 47 * 60, now), "47m");
    }

    function test_under_a_minute_shows_less_than_a_minute() {
        compare(Format.remainingLabel(now + 30, now), "<1m");
    }

    function test_past_deadline_is_expired() {
        compare(Format.remainingLabel(now - 1, now), "expired");
    }

    function test_exactly_at_deadline_is_expired() {
        compare(Format.remainingLabel(now, now), "expired");
    }

    function test_urgent_under_an_hour() {
        compare(Format.isUrgent(now + 30 * 60, now), true);
    }

    function test_not_urgent_over_an_hour() {
        compare(Format.isUrgent(now + 3 * hour, now), false);
    }

    function test_expired_counts_as_urgent() {
        compare(Format.isUrgent(now - 5, now), true);
    }
}
