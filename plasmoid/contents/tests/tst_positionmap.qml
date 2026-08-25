import QtQuick
import QtTest
import "../ui"

TestCase {
    id: testCase
    name: "PositionMap"
    when: windowShown
    visible: true
    width: 400
    height: 300

    PositionMap {
        id: positions
        tileWidth: 100
        tileHeight: 100
        canvasWidth: 400
        canvasHeight: 300
    }

    function init() {
        positions.load("{}");
    }

    function test_unknown_name_has_no_position() {
        verify(!positions.has("nope"));
        compare(positions.positionFor("nope"), null);
    }

    function test_place_then_read_back() {
        positions.place("a.txt", 40, 12);
        verify(positions.has("a.txt"));
        compare(positions.positionFor("a.txt").x, 40);
        compare(positions.positionFor("a.txt").y, 12);
    }

    function test_place_clamps_into_the_canvas() {
        positions.place("a.txt", 9999, -50);
        compare(positions.positionFor("a.txt").x, 300); // 400 - 100
        compare(positions.positionFor("a.txt").y, 0);
    }

    function test_place_clamps_to_zero_when_canvas_smaller_than_tile() {
        positions.canvasWidth = 60;
        positions.canvasHeight = 60;
        positions.place("a.txt", 500, 500);
        compare(positions.positionFor("a.txt").x, 0);
        compare(positions.positionFor("a.txt").y, 0);
        positions.canvasWidth = 400;
        positions.canvasHeight = 300;
    }

    function test_serialize_round_trips() {
        positions.place("a.txt", 40, 12);
        positions.place("b.txt", 200, 100);
        const json = positions.serialize();

        positions.load("{}");
        verify(!positions.has("a.txt"));

        positions.load(json);
        compare(positions.positionFor("a.txt").x, 40);
        compare(positions.positionFor("b.txt").y, 100);
    }

    function test_load_survives_garbage() {
        positions.place("a.txt", 40, 12);
        positions.load("not json at all");
        verify(!positions.has("a.txt"));
    }

    function test_autoplace_uses_the_first_slot_when_empty() {
        positions.autoPlace("a.txt");
        compare(positions.positionFor("a.txt").x, 0);
        compare(positions.positionFor("a.txt").y, 0);
    }

    function test_autoplace_skips_occupied_slots_in_reading_order() {
        positions.place("a.txt", 0, 0);
        positions.autoPlace("b.txt");
        compare(positions.positionFor("b.txt").x, 100);
        compare(positions.positionFor("b.txt").y, 0);
    }

    function test_autoplace_wraps_to_the_next_row() {
        positions.place("a.txt", 0, 0);
        positions.place("b.txt", 100, 0);
        positions.place("c.txt", 200, 0);
        positions.place("d.txt", 300, 0);
        positions.autoPlace("e.txt");
        compare(positions.positionFor("e.txt").x, 0);
        compare(positions.positionFor("e.txt").y, 100);
    }

    function test_autoplace_leaves_an_existing_position_alone() {
        positions.place("a.txt", 250, 40);
        positions.autoPlace("a.txt");
        compare(positions.positionFor("a.txt").x, 250);
        compare(positions.positionFor("a.txt").y, 40);
    }

    function test_clampall_pulls_items_back_after_a_shrink() {
        positions.place("a.txt", 300, 200);
        positions.canvasWidth = 200;
        positions.canvasHeight = 150;
        positions.clampAll();
        compare(positions.positionFor("a.txt").x, 100); // 200 - 100
        compare(positions.positionFor("a.txt").y, 50);  // 150 - 100
        positions.canvasWidth = 400;
        positions.canvasHeight = 300;
    }

    function test_prune_drops_names_that_are_gone() {
        positions.place("a.txt", 0, 0);
        positions.place("b.txt", 100, 0);
        positions.prune(["b.txt"]);
        verify(!positions.has("a.txt"));
        verify(positions.has("b.txt"));
    }

    function test_updated_fires_on_place() {
        updatedSpy.clear();
        positions.place("a.txt", 10, 10);
        compare(updatedSpy.count, 1);
    }

    SignalSpy {
        id: updatedSpy
        target: positions
        signalName: "updated"
    }
}
