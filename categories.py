ROOT = "MKRShift Nodes"

# Core direction nodes.
CORE_CHARACTER = f"{ROOT}/Core/Character"
CORE_CAMERA = f"{ROOT}/Core/Camera"
CORE_LAYOUT = f"{ROOT}/Core/Layout"

# Inspection and tooling nodes.
INSPECT_COMPARE = f"{ROOT}/Inspect/Compare"
INSPECT_DEBUG = f"{ROOT}/Inspect/Debug"
INSPECT_PREVIEW = f"{ROOT}/Inspect/Preview"

# Color pipeline nodes.
COLOR_LUT = f"{ROOT}/Color/LUT"
COLOR_GRADE = f"{ROOT}/Color/Grade"
COLOR_TOOLS = f"{ROOT}/Color/Tools"
COLOR_ANALYZE = f"{ROOT}/Color/Analyze"

# Effects pipeline nodes.
VFX_ROOT = f"{ROOT}/VFX"
FX_PHOTO = f"{VFX_ROOT}/Photo"
FX_STYLIZE = f"{VFX_ROOT}/Stylize"
FX_CONCEPT = f"{VFX_ROOT}/Concept"
FX_PLAY = f"{VFX_ROOT}/Play"
FX_OPTICS = f"{VFX_ROOT}/Optics"
FX_DISTORT = f"{VFX_ROOT}/Distortion"

# Utility nodes.
UTILITY_MASK = f"{ROOT}/Utility/Mask"
UTILITY_RESIZE = f"{ROOT}/Utility/Resize"
UTILITY_LAYOUT = f"{ROOT}/Utility/Layout"
UTILITY_SHADER = f"{ROOT}/Utility/Shader"
UTILITY_PHOTO = f"{ROOT}/Utility/Photo"

# Surface workflow nodes.
SURFACE_ROOT = f"{ROOT}/Surface"
SURFACE_MAPS = f"{SURFACE_ROOT}/Maps"
SURFACE_TEXTURE = f"{SURFACE_ROOT}/Texture"
SURFACE_TECH_ART = f"{SURFACE_ROOT}/Tech Art"

# Backward compatibility aliases.
UTILITY_MAPS = SURFACE_MAPS
UTILITY_TEXTURE = SURFACE_TEXTURE
UTILITY_TECH_ART = SURFACE_TECH_ART

# Media workflow taxonomy.
MEDIA_ROOT = f"{ROOT}/Media"
MEDIA_IO = f"{MEDIA_ROOT}/IO"
MEDIA_ANALYSIS = f"{MEDIA_ROOT}/Analysis"
MEDIA_TIMELINE = f"{MEDIA_ROOT}/Timeline"
MEDIA_WATERMARK = f"{MEDIA_ROOT}/Watermark"
MEDIA_VIDEO_EDIT = f"{MEDIA_ROOT}/Video/Edit"
MEDIA_VIDEO_UTILITY = f"{MEDIA_ROOT}/Video/Utility"
MEDIA_VIDEO_FX = f"{MEDIA_ROOT}/Video/FX"
MEDIA_AUDIO_UTILITY = f"{MEDIA_ROOT}/Audio/Utility"
MEDIA_AUDIO_FX = f"{MEDIA_ROOT}/Audio/FX"

# Backward compatibility alias.
UTILITY_MEDIA = MEDIA_ROOT

# Social workflow nodes.
SOCIAL_BUILDER = f"{ROOT}/Social/Builder"
SOCIAL_UTILS = f"{ROOT}/Social/Utils"

# Performance capture and retarget nodes.
PERFORMANCE_ROOT = f"{ROOT}/Performance"
PERFORMANCE_FACE = f"{PERFORMANCE_ROOT}/Face"
PERFORMANCE_POSE = f"{PERFORMANCE_ROOT}/Pose"
PERFORMANCE_ANALYSIS = f"{PERFORMANCE_ROOT}/Analysis"

# Studio workflow nodes.
STUDIO_ROOT = f"{ROOT}/Studio"
STUDIO_PREP = f"{STUDIO_ROOT}/Prep"
STUDIO_REVIEW = f"{STUDIO_ROOT}/Review"
STUDIO_BOARDS = f"{STUDIO_ROOT}/Boards"
STUDIO_DELIVERY = f"{STUDIO_ROOT}/Delivery"

# G-code workflow nodes.
GCODE_ROOT = f"{ROOT}/G-code"
GCODE_INPUT = f"{GCODE_ROOT}/Input"
GCODE_PRINTER = f"{GCODE_ROOT}/Printer"
GCODE_GENERATE = f"{GCODE_ROOT}/Generate"
GCODE_ANALYZE = f"{GCODE_ROOT}/Analyze"
GCODE_MODIFY = f"{GCODE_ROOT}/Modify"
GCODE_PREVIEW = f"{GCODE_ROOT}/Preview"
GCODE_SLICE = f"{GCODE_ROOT}/Slice"
GCODE_EXPORT = f"{GCODE_ROOT}/Export"
