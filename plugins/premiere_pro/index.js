function parseJsonOrEmpty(raw) {
  try {
    const parsed = JSON.parse(String(raw || "").trim() || "{}");
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch (error) {
    return {};
  }
}

function buildPremiereBridgeSpec(sequencePayload, exportPlan, transportPlan, endpointPlan) {
  return {
    sequence: parseJsonOrEmpty(sequencePayload),
    exportPlan: parseJsonOrEmpty(exportPlan),
    transportPlan: parseJsonOrEmpty(transportPlan),
    endpointPlan: parseJsonOrEmpty(endpointPlan),
  };
}

function buildPremiereImagePayload(sequencePayload, preferredSlot = "") {
  const sequence = parseJsonOrEmpty(sequencePayload);
  const clips = Array.isArray(sequence.clips) ? sequence.clips : [];
  const preferred = String(preferredSlot || "").toLowerCase();
  let chosen = clips.find((clip) =>
    preferred && String(clip.slot || clip.name || clip.type || "").toLowerCase().includes(preferred),
  );
  if (!chosen) chosen = clips[0] || {};
  return {
    schema: "mkrshift_premiere_image_payload_v1",
    host: "premiere_pro",
    sequence_name: sequence.sequence_name || "Sequence 01",
    images: chosen.path
      ? [
          {
            slot: chosen.slot || chosen.type || "clip",
            path: chosen.path,
            clip_name: chosen.name || "Clip 1",
          },
        ]
      : [],
  };
}

function buildPremiereImageOutputSpec(imageOutputPlan, transportPlan, endpointPlan) {
  return {
    schema: "mkrshift_premiere_image_output_spec_v1",
    imageOutputPlan: parseJsonOrEmpty(imageOutputPlan),
    transportPlan: parseJsonOrEmpty(transportPlan),
    endpointPlan: parseJsonOrEmpty(endpointPlan),
  };
}

console.log("MKRShift Premiere Plugin loaded");
