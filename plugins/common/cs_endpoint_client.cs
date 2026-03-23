using System.Collections.Generic;

namespace MKRShift.PluginCommon
{
    public static class EndpointClient
    {
        public static Dictionary<string, object> BuildHeaders(Dictionary<string, object> endpointPlan)
        {
            var headers = new Dictionary<string, object>
            {
                { "Content-Type", "application/json" }
            };

            if (endpointPlan == null)
            {
                return headers;
            }

            if (endpointPlan.TryGetValue("auth_mode", out var authModeObj) &&
                endpointPlan.TryGetValue("auth_value", out var authValueObj))
            {
                var authMode = authModeObj?.ToString() ?? "";
                var authValue = authValueObj?.ToString() ?? "";
                var authKey = endpointPlan.ContainsKey("auth_key") ? endpointPlan["auth_key"]?.ToString() ?? "Authorization" : "Authorization";
                if (authMode == "bearer" && authValue.Length > 0)
                {
                    headers[authKey] = $"Bearer {authValue}";
                }
                else if (authMode == "header" && authValue.Length > 0)
                {
                    headers[authKey] = authValue;
                }
            }

            return headers;
        }
    }
}
