import QtQuick
import org.kde.plasma.plasma5support as P5Support

Item {
    id: drawerModel

    property string statePath: ""
    property real lifetimeSeconds: 24 * 3600
    property alias model: items
    property real now: 0

    signal loaded()

    ListModel { id: items }

    // Qt disables XMLHttpRequest GET on local files unless QML_XHR_ALLOW_FILE_READ=1
    // is set in the environment, which we cannot rely on inside plasmashell. The
    // state file is read through the executable engine instead, matching the rest
    // of the design where all filesystem access happens outside QML.
    function reload() {
        if (!statePath) {
            return;
        }
        reader.connectSource("cat -- '" + statePath.replace(/'/g, "'\\''") + "'");
    }

    P5Support.DataSource {
        id: reader
        engine: "executable"
        connectedSources: []

        onNewData: function (source, data) {
            disconnectSource(source);
            drawerModel.now = Date.now() / 1000;
            drawerModel._apply(data["stdout"] || "");
        }
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
