import QtQuick
import org.kde.plasma.plasma5support as P5Support

Item {
    id: backend

    property string cli: ""
    signal finished(string command, int exitCode)

    function quote(value) {
        return "'" + String(value).replace(/'/g, "'\\''") + "'";
    }

    function run(command) {
        executable.connectSource(command);
    }

    function add(url) {
        run(quote(cli) + " add " + quote(url));
    }

    function remove(name) {
        run(quote(cli) + " remove " + quote(name));
    }

    function openPath(path) {
        run("xdg-open " + quote(path));
    }

    function reveal(path) {
        run("dolphin --select " + quote(path));
    }

    function setConfig(key, value) {
        run(quote(cli) + " config set " + quote(key) + " " + quote(value));
    }

    P5Support.DataSource {
        id: executable
        engine: "executable"
        connectedSources: []

        onNewData: function (source, data) {
            disconnectSource(source);
            backend.finished(source, data["exit code"]);
        }
    }
}
