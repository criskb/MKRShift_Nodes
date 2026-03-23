from MKRShiftBridgePanel import show_mkrshift_bridge_panel


def add_mkrshift_menu():
    return {
        "menu": "MKRShift",
        "command": "show_mkrshift_bridge_panel()",
        "label": "Open Bridge Panel",
        "gizmo_command": "nuke.createNode('MKRShiftBridge')",
        "gizmo_label": "Create Bridge Gizmo",
    }
