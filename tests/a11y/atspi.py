# AT-SPI2 tree walker over the minimal stdlib D-Bus client.
import dbusmin

ACC = "org.a11y.atspi.Accessible"
APP = "org.a11y.atspi.Application"
PROPS = "org.freedesktop.DBus.Properties"
ROOT = "/org/a11y/atspi/accessible/root"

# org.a11y.atspi.StateType, in enum order (atspi-constants.h).
STATE_NAMES = [
    "invalid", "active", "armed", "busy", "checked", "collapsed", "defunct",
    "editable", "enabled", "expandable", "expanded", "focusable", "focused",
    "has-tooltip", "horizontal", "iconified", "modal", "multi-line",
    "multiselectable", "opaque", "pressed", "resizable", "selectable",
    "selected", "sensitive", "showing", "single-line", "stale", "transient",
    "vertical", "visible", "manages-descendants", "indeterminate", "required",
    "truncated", "animated", "invalid-entry", "supports-autocompletion",
    "selection-text", "is-default", "visited", "checkable", "has-popup",
    "read-only",
]


def decode_states(words):
    out = []
    for w, word in enumerate(words or []):
        for bit in range(32):
            if word & (1 << bit):
                i = w * 32 + bit
                out.append(STATE_NAMES[i] if i < len(STATE_NAMES) else "bit%d" % i)
    return out


def get_prop(bus, dest, path, iface, name):
    return bus.call(dest, path, PROPS, "Get", "ss", (iface, name))[0]


def apps_from_registry(bus):
    """The registry's desktop root lists every application that registered."""
    return bus.call("org.a11y.atspi.Registry", ROOT, ACC, "GetChildren")[0]


def connections(bus):
    """Every unique bus name on the a11y bus, with pid and toolkit."""
    names = bus.call("org.freedesktop.DBus", "/org/freedesktop/DBus",
                     "org.freedesktop.DBus", "ListNames")[0]
    out = []
    for n in names:
        if not n.startswith(":") or n == bus.unique_name:
            continue
        try:
            pid = bus.call("org.freedesktop.DBus", "/org/freedesktop/DBus",
                           "org.freedesktop.DBus", "GetConnectionUnixProcessID",
                           "s", (n,), timeout=2.0)[0]
        except dbusmin.DBusError:
            continue
        toolkit = None
        version = None
        try:
            toolkit = bus.call(n, ROOT, PROPS, "Get", "ss",
                               (APP, "ToolkitName"), timeout=2.0)[0]
            version = bus.call(n, ROOT, PROPS, "Get", "ss",
                               (APP, "Version"), timeout=2.0)[0]
        except dbusmin.DBusError:
            pass
        out.append({"name": n, "pid": pid, "toolkit": toolkit, "version": version})
    return out


def find_qt_connection(bus, pid):
    """CLAUDE.md lesson from the investigation: key on ToolkitName, never Name."""
    for c in connections(bus):
        if c["pid"] == pid and c["toolkit"] == "Qt":
            return c
    return None


def node(bus, dest, path):
    """Read one accessible object into a plain dict."""
    n = {"dest": dest, "path": path}
    for key, iface, prop in (("name", ACC, "Name"),
                             ("description", ACC, "Description")):
        try:
            n[key] = get_prop(bus, dest, path, iface, prop)
        except dbusmin.DBusError:
            n[key] = None
    try:
        n["role"] = bus.call(dest, path, ACC, "GetRoleName")[0]
    except dbusmin.DBusError:
        n["role"] = None
    try:
        n["interfaces"] = bus.call(dest, path, ACC, "GetInterfaces")[0]
    except dbusmin.DBusError:
        n["interfaces"] = []
    try:
        n["states"] = bus.call(dest, path, ACC, "GetState")[0]
    except dbusmin.DBusError:
        n["states"] = []
    n["state_names"] = decode_states(n["states"])
    # The sink CLAUDE.md rule 5 forgot: an editable field's content is
    # published through org.a11y.atspi.Text, not through Name or Description.
    n["text"] = None
    if "org.a11y.atspi.Text" in n["interfaces"]:
        try:
            n["text"] = bus.call(dest, path, "org.a11y.atspi.Text",
                                 "GetText", "ii", (0, -1))[0]
        except dbusmin.DBusError:
            pass
    return n


def children(bus, dest, path):
    try:
        return bus.call(dest, path, ACC, "GetChildren")[0]
    except dbusmin.DBusError:
        return []


def walk(bus, dest, path=ROOT, depth=0, max_depth=40, out=None):
    if out is None:
        out = []
    n = node(bus, dest, path)
    n["depth"] = depth
    out.append(n)
    if depth < max_depth:
        for cdest, cpath in children(bus, dest, path):
            walk(bus, cdest or dest, cpath, depth + 1, max_depth, out)
    return out


def render(nodes):
    lines = []
    for n in nodes:
        label = "  " * n["depth"] + "%s %r" % (n["role"], n["name"])
        if n.get("description"):
            label += " desc=%r" % n["description"]
        if n.get("text") is not None:
            label += " text=%r" % n["text"]
        interesting = [x for x in n.get("state_names", [])
                       if x in ("focused", "focusable", "selected", "checked",
                                "checkable", "showing", "visible", "editable",
                                "read-only")]
        if interesting:
            label += "  [%s]" % ",".join(interesting)
        lines.append(label)
    return "\n".join(lines)
