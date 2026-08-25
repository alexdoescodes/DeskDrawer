import QtQuick
import QtTest
import "../ui"

TestCase {
    id: testCase
    name: "ItemTile"
    when: windowShown
    visible: true
    width: 200
    height: 200

    property int activatedCount: 0
    property int removeCount: 0
    property int revealCount: 0

    ItemTile {
        id: tile
        anchors.fill: parent
        itemName: "probe.txt"
        origin: "/tmp/probe.txt"
        iconName: "text-x-generic"
        onActivated: testCase.activatedCount++
        onRemoveRequested: testCase.removeCount++
        onRevealRequested: testCase.revealCount++
    }

    function init() {
        testCase.activatedCount = 0;
        testCase.removeCount = 0;
        testCase.revealCount = 0;
    }

    // Left-button behaviour is deliberately NOT tested here. qmltestrunner
    // cannot synthesize a realistic double click: its events carry timestamps
    // that do not advance, so both MouseArea.onDoubleClicked and
    // TapHandler.onDoubleTapped see two unrelated single taps, and
    // mouseDoubleClickSequence() fakes the DblClick event outright - it passed
    // against an ItemTile that could not be double clicked at all in practice.
    // Verify the left button with real input instead; see README.

    function test_middle_click_removes_from_drawer() {
        mouseClick(tile, tile.width / 2, tile.height / 2, Qt.MiddleButton);
        compare(testCase.removeCount, 1, "middle click should remove");
        compare(testCase.revealCount, 0, "middle click no longer reveals");
    }

    function test_middle_click_does_not_open() {
        mouseClick(tile, tile.width / 2, tile.height / 2, Qt.MiddleButton);
        compare(testCase.activatedCount, 0, "middle click must not open");
    }
}
