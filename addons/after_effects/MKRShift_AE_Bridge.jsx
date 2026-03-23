function MKRShiftLoadJsonFile(pathText) {
    var file = new File(pathText || "");
    if (!file.exists) {
        return {};
    }
    file.open("r");
    var data = file.read();
    file.close();
    try {
        return JSON.parse(data);
    } catch (error) {
        return {};
    }
}

function MKRShiftBuildRenderSpec(renderPlanPath, transportPlanPath) {
    return {
        renderPlan: MKRShiftLoadJsonFile(renderPlanPath),
        transportPlan: MKRShiftLoadJsonFile(transportPlanPath)
    };
}

function MKRShiftBuildImagePayload(compPacketPath, preferredSlot) {
    var packet = MKRShiftLoadJsonFile(compPacketPath);
    var layers = packet.layers instanceof Array ? packet.layers : [];
    var preferred = String(preferredSlot || "").toLowerCase();
    var chosen = {};
    var i;
    for (i = 0; i < layers.length; i += 1) {
        var layer = layers[i];
        var slot = String(layer.slot || layer.name || "").toLowerCase();
        if (preferred && slot.indexOf(preferred) !== -1) {
            chosen = layer;
            break;
        }
    }
    if (!chosen.path && layers.length) {
        chosen = layers[0];
    }
    return {
        schema: "mkrshift_after_effects_image_payload_v1",
        host: "after_effects",
        comp_name: packet.comp_name || "Comp 1",
        images: chosen.path ? [{
            slot: chosen.slot || chosen.name || "footage",
            path: chosen.path,
            layer_name: chosen.name || "Layer 1"
        }] : []
    };
}

function MKRShiftBuildImageOutputSpec(imageOutputPlanPath, transportPlanPath, endpointPlanPath) {
    return {
        schema: "mkrshift_after_effects_image_output_spec_v1",
        imageOutputPlan: MKRShiftLoadJsonFile(imageOutputPlanPath),
        transportPlan: MKRShiftLoadJsonFile(transportPlanPath),
        endpointPlan: MKRShiftLoadJsonFile(endpointPlanPath)
    };
}

function MKRShiftBuildPlaybackSpec(renderPlanPath, startFrame, loopMode, triggerMode) {
    return {
        schema: "mkrshift_after_effects_playback_spec_v1",
        renderPlan: MKRShiftLoadJsonFile(renderPlanPath),
        startFrame: parseInt(startFrame || 1, 10) || 1,
        loopMode: String(loopMode || "once"),
        triggerMode: String(triggerMode || "manual")
    };
}

function MKRShiftBuildEndpointHeaders(endpointPlan) {
    var headers = {"Content-Type": "application/json"};
    if (!endpointPlan) {
        return headers;
    }
    if (endpointPlan.default_headers) {
        for (var key in endpointPlan.default_headers) {
            if (endpointPlan.default_headers.hasOwnProperty(key)) {
                headers[key] = String(endpointPlan.default_headers[key]);
            }
        }
    }
    if (endpointPlan.auth_mode === "bearer" && endpointPlan.auth_value) {
        headers[endpointPlan.auth_key || "Authorization"] = "Bearer " + endpointPlan.auth_value;
    } else if (endpointPlan.auth_mode === "header" && endpointPlan.auth_value) {
        headers[endpointPlan.auth_key || "Authorization"] = endpointPlan.auth_value;
    }
    return headers;
}

function MKRShiftHttpRequest(method, url, headers, bodyText) {
    var socket = new Socket();
    if (!socket.open(url.replace(/^https?:\/\//, ""), "binary")) {
        return {ok: false, error: "socket_open_failed", url: url};
    }
    var lines = [method + " / HTTP/1.1"];
    var headerKey;
    for (headerKey in headers) {
        if (headers.hasOwnProperty(headerKey)) {
            lines.push(headerKey + ": " + headers[headerKey]);
        }
    }
    lines.push("Host: " + url.replace(/^https?:\/\//, "").split("/")[0]);
    lines.push("Connection: close");
    lines.push("");
    lines.push(bodyText || "");
    socket.write(lines.join("\r\n"));
    var response = socket.read(999999);
    socket.close();
    return {ok: true, raw: response};
}

function MKRShiftSubmitPayload(endpointPlanPath, payloadPath) {
    var endpointPlan = MKRShiftLoadJsonFile(endpointPlanPath);
    var payload = MKRShiftLoadJsonFile(payloadPath);
    var baseUrl = String(endpointPlan.base_url || "").replace(/\/$/, "");
    var submitPath = String(endpointPlan.submit_path || "/mkrshift/submit");
    return MKRShiftHttpRequest("POST", baseUrl + submitPath, MKRShiftBuildEndpointHeaders(endpointPlan), JSON.stringify(payload));
}

function MKRShiftPollStatus(endpointPlanPath, jobId) {
    var endpointPlan = MKRShiftLoadJsonFile(endpointPlanPath);
    var baseUrl = String(endpointPlan.base_url || "").replace(/\/$/, "");
    var pollPath = String(endpointPlan.poll_path || "/mkrshift/status").replace(/\/$/, "");
    var url = baseUrl + pollPath + (jobId ? "/" + encodeURIComponent(String(jobId)) : "");
    return MKRShiftHttpRequest("GET", url, MKRShiftBuildEndpointHeaders(endpointPlan), "");
}

function MKRShiftBuildPanel(thisObj) {
    var panel = (thisObj instanceof Panel) ? thisObj : new Window("palette", "MKRShift AE Bridge", undefined, {resizeable:true});
    panel.orientation = "column";
    panel.add("statictext", undefined, "MKRShift After Effects Bridge");
    panel.layout.layout(true);
    return panel;
}

var mkrshiftPanel = MKRShiftBuildPanel(this);
if (mkrshiftPanel instanceof Window) {
    mkrshiftPanel.center();
    mkrshiftPanel.show();
}
