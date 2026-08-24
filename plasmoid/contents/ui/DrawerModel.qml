import QtQuick

Item {
    id: drawerModel

    property string statePath: ""
    property real lifetimeSeconds: 24 * 3600
    property alias model: items
    property real now: 0

    signal loaded()

    ListModel { id: items }

    function reload() {
        const request = new XMLHttpRequest();
        request.onreadystatechange = function () {
            if (request.readyState !== XMLHttpRequest.DONE) {
                return;
            }
            drawerModel.now = Date.now() / 1000;
            drawerModel._apply(request.responseText);
        };
        request.open("GET", "file://" + statePath);
        request.send();
    }

    function _apply(text) {
        let parsed = {};
        try {
            parsed = JSON.parse(text || "{}");
        } catch (error) {
            parsed = {};
        }

        items.clear();
        const names = Object.keys(parsed).sort();
        for (let i = 0; i < names.length; ++i) {
            const entry = parsed[names[i]];
            items.append({
                name: entry.name,
                origin: entry.origin,
                dropped: entry.dropped,
                lastActivity: entry.last_activity,
                isDir: entry.is_dir === true,
                originExists: entry.exists !== false,
                iconName: entry.icon || "unknown"
            });
        }
        loaded();
    }

    Timer {
        interval: 60000
        running: true
        repeat: true
        triggeredOnStart: true
        onTriggered: drawerModel.reload()
    }

    Timer {
        interval: 30000
        running: true
        repeat: true
        onTriggered: drawerModel.now = Date.now() / 1000
    }
}
