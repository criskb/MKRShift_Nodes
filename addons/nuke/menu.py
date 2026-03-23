import nuke

from MKRShiftBridgePanel import show_mkrshift_bridge_panel


def add_mkrshift_menu():
    menu = nuke.menu("Nuke").addMenu("MKRShift")
    menu.addCommand("Open Bridge Panel", "show_mkrshift_bridge_panel()")
    menu.addCommand("Create Bridge Gizmo", "nuke.createNode('MKRShiftBridge')")


add_mkrshift_menu()
