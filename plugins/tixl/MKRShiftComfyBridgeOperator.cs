using System;
using System.Collections.Generic;
using System.IO;
using System.Net.Http;
using System.Text;
using System.Text.Json;

namespace MKRShift.TiXL
{
    public class MKRShiftComfyBridgeOperator
    {
        public string LastPacketPath { get; private set; } = string.Empty;
        public Dictionary<string, object> LastPacket { get; private set; } = new();

        public Dictionary<string, object> LoadPacket(string path)
        {
            LastPacketPath = path ?? string.Empty;
            if (string.IsNullOrWhiteSpace(LastPacketPath) || !File.Exists(LastPacketPath))
            {
                LastPacket = new Dictionary<string, object>();
                return LastPacket;
            }

            var raw = File.ReadAllText(LastPacketPath);
            LastPacket = JsonSerializer.Deserialize<Dictionary<string, object>>(raw) ?? new Dictionary<string, object>();
            return LastPacket;
        }

        public Dictionary<string, object> LoadTransportPlan(string path)
        {
            if (string.IsNullOrWhiteSpace(path) || !File.Exists(path))
            {
                return new Dictionary<string, object>();
            }

            var raw = File.ReadAllText(path);
            return JsonSerializer.Deserialize<Dictionary<string, object>>(raw) ?? new Dictionary<string, object>();
        }

        public Dictionary<string, object> LoadEndpointPlan(string path)
        {
            if (string.IsNullOrWhiteSpace(path) || !File.Exists(path))
            {
                return new Dictionary<string, object>();
            }

            var raw = File.ReadAllText(path);
            return JsonSerializer.Deserialize<Dictionary<string, object>>(raw) ?? new Dictionary<string, object>();
        }

        public Dictionary<string, string> BuildEndpointHeaders(string path)
        {
            var headers = new Dictionary<string, string> { ["Content-Type"] = "application/json" };
            var plan = LoadEndpointPlan(path);
            if (plan.TryGetValue("default_headers", out var defaultHeadersObj) && defaultHeadersObj is JsonElement defaultHeaders && defaultHeaders.ValueKind == JsonValueKind.Object)
            {
                foreach (var property in defaultHeaders.EnumerateObject())
                {
                    headers[property.Name] = property.Value.ToString();
                }
            }

            var authMode = plan.TryGetValue("auth_mode", out var authModeObj) ? authModeObj?.ToString() ?? string.Empty : string.Empty;
            var authKey = plan.TryGetValue("auth_key", out var authKeyObj) ? authKeyObj?.ToString() ?? "Authorization" : "Authorization";
            var authValue = plan.TryGetValue("auth_value", out var authValueObj) ? authValueObj?.ToString() ?? string.Empty : string.Empty;
            if (authMode == "bearer" && !string.IsNullOrWhiteSpace(authValue))
            {
                headers[authKey] = $"Bearer {authValue}";
            }
            else if (authMode == "header" && !string.IsNullOrWhiteSpace(authValue))
            {
                headers[authKey] = authValue;
            }
            return headers;
        }

        public Dictionary<string, object> BuildOutgoingPayload(
            string projectName,
            string graphName,
            string operatorName,
            string transport,
            string sourceKind,
            int width,
            int height,
            double bpm)
        {
            return new Dictionary<string, object>
            {
                ["schema"] = "mkrshift_tixl_bridge_v1",
                ["source"] = "tixl",
                ["project_name"] = projectName ?? "TiXL",
                ["graph_name"] = graphName ?? "MKRShiftBridge",
                ["operator_name"] = operatorName ?? "MKRShiftComfyBridge",
                ["transport"] = transport ?? "file",
                ["source_kind"] = sourceKind ?? "texture",
                ["width"] = width,
                ["height"] = height,
                ["bpm"] = bpm,
                ["layers"] = new object[] { },
            };
        }

        public Dictionary<string, object> BuildFrameSpec(string packetPath, string framePlanPath, string transportPlanPath, string endpointPlanPath)
        {
            return new Dictionary<string, object>
            {
                ["packet"] = LoadPacket(packetPath),
                ["framePlan"] = LoadPacket(framePlanPath),
                ["transportPlan"] = LoadTransportPlan(transportPlanPath),
                ["endpointPlan"] = LoadEndpointPlan(endpointPlanPath),
            };
        }

        public Dictionary<string, object> BuildImagePayload(string packetPath, string preferredSlot = "")
        {
            var packet = LoadPacket(packetPath);
            var images = new List<Dictionary<string, object>>();
            if (packet.TryGetValue("layers", out var layersObj) && layersObj is JsonElement layers && layers.ValueKind == JsonValueKind.Array)
            {
                var preferred = (preferredSlot ?? string.Empty).Trim().ToLowerInvariant();
                JsonElement? chosen = null;
                foreach (var layer in layers.EnumerateArray())
                {
                    var slot = layer.TryGetProperty("name", out var name) ? name.ToString() : string.Empty;
                    var kind = layer.TryGetProperty("kind", out var kindProp) ? kindProp.ToString() : string.Empty;
                    if (!string.IsNullOrWhiteSpace(preferred) && (slot.ToLowerInvariant().Contains(preferred) || kind.ToLowerInvariant().Contains(preferred)))
                    {
                        chosen = layer;
                        break;
                    }
                    if (chosen == null)
                    {
                        chosen = layer;
                    }
                }
                if (chosen.HasValue && chosen.Value.TryGetProperty("path", out var pathProp))
                {
                    images.Add(new Dictionary<string, object>
                    {
                        ["slot"] = chosen.Value.TryGetProperty("kind", out var chosenKind) ? chosenKind.ToString() : "texture",
                        ["path"] = pathProp.ToString(),
                        ["layer_name"] = chosen.Value.TryGetProperty("name", out var chosenName) ? chosenName.ToString() : "Layer",
                    });
                }
            }

            return new Dictionary<string, object>
            {
                ["schema"] = "mkrshift_tixl_image_payload_v1",
                ["host"] = "tixl",
                ["packet"] = packet,
                ["images"] = images,
            };
        }

        public Dictionary<string, object> BuildImageOutputSpec(string imageOutputPlanPath, string transportPlanPath, string endpointPlanPath)
        {
            return new Dictionary<string, object>
            {
                ["schema"] = "mkrshift_tixl_image_output_spec_v1",
                ["imageOutputPlan"] = LoadPacket(imageOutputPlanPath),
                ["transportPlan"] = LoadTransportPlan(transportPlanPath),
                ["endpointPlan"] = LoadEndpointPlan(endpointPlanPath),
            };
        }

        public Dictionary<string, object> BuildPlaybackSpec(string framePlanPath, int startFrame = 1, string loopMode = "once", string triggerMode = "manual")
        {
            return new Dictionary<string, object>
            {
                ["schema"] = "mkrshift_tixl_playback_spec_v1",
                ["framePlan"] = LoadPacket(framePlanPath),
                ["startFrame"] = startFrame,
                ["loopMode"] = string.IsNullOrWhiteSpace(loopMode) ? "once" : loopMode,
                ["triggerMode"] = string.IsNullOrWhiteSpace(triggerMode) ? "manual" : triggerMode,
            };
        }

        public Dictionary<string, object> SubmitPayload(string endpointPlanPath, Dictionary<string, object> payload = null)
        {
            var endpointPlan = LoadEndpointPlan(endpointPlanPath);
            var baseUrl = endpointPlan.TryGetValue("base_url", out var baseUrlObj) ? (baseUrlObj?.ToString() ?? string.Empty).TrimEnd('/') : string.Empty;
            var submitPath = endpointPlan.TryGetValue("submit_path", out var submitPathObj) ? submitPathObj?.ToString() ?? "/mkrshift/submit" : "/mkrshift/submit";
            var timeoutMs = endpointPlan.TryGetValue("timeout_ms", out var timeoutObj) && int.TryParse(timeoutObj?.ToString(), out var timeout) ? timeout : 30000;
            var url = $"{baseUrl}{submitPath}";
            using var client = new HttpClient { Timeout = TimeSpan.FromMilliseconds(timeoutMs) };
            foreach (var header in BuildEndpointHeaders(endpointPlanPath))
            {
                if (header.Key.Equals("Content-Type", StringComparison.OrdinalIgnoreCase))
                {
                    continue;
                }
                client.DefaultRequestHeaders.TryAddWithoutValidation(header.Key, header.Value);
            }
            var body = JsonSerializer.Serialize(payload ?? BuildOutgoingPayload("TiXL", "MKRShiftBridge", "MKRShiftComfyBridge", "file", "texture", 1920, 1080, 120.0));
            using var content = new StringContent(body, Encoding.UTF8, "application/json");
            var response = client.PostAsync(url, content).GetAwaiter().GetResult();
            var responseBody = response.Content.ReadAsStringAsync().GetAwaiter().GetResult();
            return JsonSerializer.Deserialize<Dictionary<string, object>>(responseBody) ?? new Dictionary<string, object>();
        }

        public Dictionary<string, object> PollStatus(string endpointPlanPath, string jobId = "")
        {
            var endpointPlan = LoadEndpointPlan(endpointPlanPath);
            var baseUrl = endpointPlan.TryGetValue("base_url", out var baseUrlObj) ? (baseUrlObj?.ToString() ?? string.Empty).TrimEnd('/') : string.Empty;
            var pollPath = endpointPlan.TryGetValue("poll_path", out var pollPathObj) ? pollPathObj?.ToString() ?? "/mkrshift/status" : "/mkrshift/status";
            var timeoutMs = endpointPlan.TryGetValue("timeout_ms", out var timeoutObj) && int.TryParse(timeoutObj?.ToString(), out var timeout) ? timeout : 30000;
            var url = $"{baseUrl}{pollPath}".TrimEnd('/');
            if (!string.IsNullOrWhiteSpace(jobId))
            {
                url = $"{url}/{jobId.Trim()}";
            }
            using var client = new HttpClient { Timeout = TimeSpan.FromMilliseconds(timeoutMs) };
            foreach (var header in BuildEndpointHeaders(endpointPlanPath))
            {
                if (header.Key.Equals("Content-Type", StringComparison.OrdinalIgnoreCase))
                {
                    continue;
                }
                client.DefaultRequestHeaders.TryAddWithoutValidation(header.Key, header.Value);
            }
            var responseBody = client.GetStringAsync(url).GetAwaiter().GetResult();
            return JsonSerializer.Deserialize<Dictionary<string, object>>(responseBody) ?? new Dictionary<string, object>();
        }
    }
}
