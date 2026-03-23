# MKRShift Blender Addon

The Blender bridge is currently packaged from the legacy compatibility path:

- `blender_extension/mkrshift_blender_bridge/`

That path is still kept alive because the install zip and existing workflow references already depend on it.

Live bridge capabilities now include:

- scene / camera / pose / material / image payload export
- image and material output-plan application
- endpoint-plan driven submit / poll from inside Blender

Longer term, the Blender addon can be fully migrated under `addons/blender/`, but for now this folder is the canonical host-integration landing page while the build/install source remains compatible.
