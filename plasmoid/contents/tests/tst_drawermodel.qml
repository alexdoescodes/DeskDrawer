import QtQuick
import QtTest
import "../ui"

TestCase {
    id: testCase
    name: "DrawerModel"
    when: windowShown

    DrawerModel {
        id: drawerModel
        statePath: Qt.resolvedUrl("fixture-state.json").toString().replace("file://", "")
    }

    readonly property string fixture: Qt.resolvedUrl("fixture-state.json").toString().replace("file://", "")

    function test_reads_state_json() {
        drawerModel.statePath = testCase.fixture;
        drawerModel.reload();
        tryCompare(drawerModel.model, "count", 2, 3000);
    }

    function test_entries_are_sorted_and_mapped() {
        drawerModel.statePath = testCase.fixture;
        drawerModel.reload();
        tryCompare(drawerModel.model, "count", 2, 3000);
        compare(drawerModel.model.get(0).name, "project");
        compare(drawerModel.model.get(0).isDir, true);
        compare(drawerModel.model.get(0).iconName, "folder");
        compare(drawerModel.model.get(1).name, "report.pdf");
        compare(drawerModel.model.get(1).origin, "/tmp/report.pdf");
        compare(drawerModel.model.get(1).originExists, true);
    }

    function test_missing_file_leaves_model_empty() {
        drawerModel.statePath = "/nonexistent/state.json";
        drawerModel.reload();
        tryCompare(drawerModel.model, "count", 0, 3000);
    }
}
