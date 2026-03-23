# MKRShift Addon Endpoint Helpers

Shared endpoint contract notes for host-side add-ons.

These helpers describe a common HTTP endpoint flow:

1. load an `mkrshift_addon_endpoint_plan_v1`
2. submit a host packet or frame/material/document plan to `submit_path`
3. poll `status_path`
4. fetch `result_path`

Host implementations can stay file-based, transport-plan based, or become fully endpoint-driven while sharing the same payload contract.
