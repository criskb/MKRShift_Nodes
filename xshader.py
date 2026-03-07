import math
import re
from functools import lru_cache
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import torch

from .categories import UTILITY_SHADER
from .xshared import to_image_batch as _to_image_batch

_SWIZZLE = {"x": 0, "r": 0, "y": 1, "g": 1, "z": 2, "b": 2, "w": 3, "a": 3}
_TYPE_PREFIX = (
    "float",
    "int",
    "bool",
    "vec2",
    "vec3",
    "vec4",
    "float2",
    "float3",
    "float4",
    "half",
    "half2",
    "half3",
    "half4",
    "fixed",
    "fixed2",
    "fixed3",
    "fixed4",
    "double",
    "uint",
)
_ASSIGN_RE = re.compile(
    r"^(?:const\s+)?"
    r"(?:(?:" + "|".join(_TYPE_PREFIX) + r")\s+)?"
    r"(?P<lhs>[A-Za-z_]\w*(?:\.[rgbaxyzw]{1,4})?)\s*"
    r"(?P<op>\+=|-=|\*=|/=|=)\s*"
    r"(?P<rhs>.+)$"
)

_DEFAULT_SHADER = """vec4 base = texture(srcTex, uv);
vec2 p = uv * 2.0 - 1.0;
float vignette = smoothstep(1.2, 0.2, length(p));
vec3 graded = base.rgb * vec3(1.04, 1.00, 0.96);
return vec4(graded * vignette, base.a);
"""


def _clamp01(arr: np.ndarray) -> np.ndarray:
    return np.clip(arr, 0.0, 1.0)


def _strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    text = re.sub(r"//.*?$", "", text, flags=re.MULTILINE)
    return text


def _find_matching_brace(text: str, start_idx: int) -> int:
    depth = 0
    for idx in range(start_idx, len(text)):
        ch = text[idx]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return idx
    return -1


def _extract_shader_body(code: str) -> str:
    for marker in ("mainImage", "main"):
        marker_match = re.search(rf"\b{marker}\b", code)
        if not marker_match:
            continue
        brace_start = code.find("{", marker_match.end())
        if brace_start < 0:
            continue
        brace_end = _find_matching_brace(code, brace_start)
        if brace_end < 0:
            return code[brace_start + 1 :]
        return code[brace_start + 1 : brace_end]
    return code


def _split_statements(code: str) -> List[str]:
    out: List[str] = []
    chunk: List[str] = []
    depth = 0
    for ch in code:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth = max(0, depth - 1)
        if ch == ";" and depth == 0:
            s = "".join(chunk).strip()
            if s:
                out.append(s)
            chunk = []
            continue
        chunk.append(ch)
    tail = "".join(chunk).strip()
    if tail:
        out.append(tail)
    return out


def _find_top_level_char(text: str, target: str) -> int:
    depth = 0
    for idx, ch in enumerate(text):
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth = max(0, depth - 1)
        elif ch == target and depth == 0:
            return idx
    return -1


def _find_ternary_colon(text: str, question_idx: int) -> int:
    depth = 0
    ternary_depth = 0
    for idx in range(question_idx + 1, len(text)):
        ch = text[idx]
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth = max(0, depth - 1)
        elif depth == 0:
            if ch == "?":
                ternary_depth += 1
            elif ch == ":":
                if ternary_depth == 0:
                    return idx
                ternary_depth -= 1
    return -1


def _convert_ternary(expr: str) -> str:
    q_idx = _find_top_level_char(expr, "?")
    if q_idx < 0:
        return expr
    c_idx = _find_ternary_colon(expr, q_idx)
    if c_idx < 0:
        return expr
    cond = _convert_ternary(expr[:q_idx].strip())
    if_true = _convert_ternary(expr[q_idx + 1 : c_idx].strip())
    if_false = _convert_ternary(expr[c_idx + 1 :].strip())
    return f"where({cond}, {if_true}, {if_false})"


def _translate_expr(expr: str) -> str:
    out = expr.strip().rstrip(";")
    out = re.sub(r"(?<=\d)f\b", "", out)
    out = re.sub(r"\bfrac\s*\(", "fract(", out)
    out = re.sub(r"\blerp\s*\(", "mix(", out)
    out = re.sub(r"\bsaturate\s*\(", "clamp01(", out)
    out = re.sub(r"([A-Za-z_]\w*)\.Sample\s*\(\s*[A-Za-z_]\w+\s*,", r"sample(\1,", out)
    out = out.replace("&&", "&").replace("||", "|")
    out = _convert_ternary(out)
    return out


def _parse_shader_statements(code: str) -> List[Tuple[str, str, str, str]]:
    cleaned = _strip_comments(code or "")
    body = _extract_shader_body(cleaned)
    statements = _split_statements(body)

    parsed: List[Tuple[str, str, str, str]] = []
    for raw in statements:
        statement = " ".join(raw.strip().split())
        if not statement:
            continue

        lowered = statement.lower()
        if lowered.startswith(
            (
                "uniform ",
                "precision ",
                "sampler2d ",
                "texture2d ",
                "samplerstate ",
                "cbuffer ",
                "struct ",
                "in ",
                "out ",
            )
        ):
            continue
        if lowered.startswith(("void main", "float4 main", "vec4 main")):
            continue
        if statement in {"{", "}"}:
            continue

        if lowered.startswith("return "):
            parsed.append(("return", "", "", _translate_expr(statement[7:].strip())))
            continue

        assign = _ASSIGN_RE.match(statement)
        if assign:
            lhs = assign.group("lhs")
            op = assign.group("op")
            rhs = _translate_expr(assign.group("rhs").strip())
            parsed.append(("assign", lhs, op, rhs))
            continue

        parsed.append(("expr", "", "", _translate_expr(statement)))

    return parsed


@lru_cache(maxsize=8)
def _uv_frag_grid(h: int, w: int) -> Tuple[np.ndarray, np.ndarray]:
    xs = np.linspace(0.0, 1.0, w, dtype=np.float32)
    ys = np.linspace(0.0, 1.0, h, dtype=np.float32)
    xg, yg = np.meshgrid(xs, ys)
    uv = np.stack([xg, yg], axis=-1).astype(np.float32, copy=False)
    frag = np.stack([xg * (w - 1), yg * (h - 1)], axis=-1).astype(np.float32, copy=False)
    return uv, frag


class ShaderValue:
    __array_priority__ = 1000

    def __init__(self, value: Any, h: int, w: int):
        self.h = int(h)
        self.w = int(w)
        self.arr = self._normalize(value, self.h, self.w)

    @staticmethod
    def _normalize(value: Any, h: int, w: int) -> np.ndarray:
        if isinstance(value, ShaderValue):
            if value.h != h or value.w != w:
                raise ValueError("ShaderValue dimensions do not match")
            return value.arr.astype(np.float32, copy=False)

        if np.isscalar(value):
            return np.full((h, w, 1), float(value), dtype=np.float32)

        arr = np.asarray(value, dtype=np.float32)
        if arr.ndim == 0:
            return np.full((h, w, 1), float(arr), dtype=np.float32)
        if arr.ndim == 1:
            if arr.shape[0] < 1 or arr.shape[0] > 4:
                raise ValueError(f"Invalid vector size: {arr.shape[0]}")
            return np.broadcast_to(arr.reshape(1, 1, -1), (h, w, arr.shape[0])).astype(np.float32, copy=True)
        if arr.ndim == 2:
            return arr[..., None].astype(np.float32, copy=False)
        if arr.ndim == 3:
            if arr.shape[0] == h and arr.shape[1] == w and 1 <= arr.shape[2] <= 4:
                return arr.astype(np.float32, copy=False)
        raise ValueError(f"Unsupported ShaderValue shape: {arr.shape}")

    @property
    def channels(self) -> int:
        return int(self.arr.shape[2])

    def _coerce(self, other: Any) -> "ShaderValue":
        return other if isinstance(other, ShaderValue) else ShaderValue(other, self.h, self.w)

    @staticmethod
    def _align(a: "ShaderValue", b: "ShaderValue") -> Tuple[np.ndarray, np.ndarray]:
        aa = a.arr
        bb = b.arr
        ca, cb = aa.shape[2], bb.shape[2]
        if ca == cb:
            return aa, bb
        if ca == 1:
            return np.repeat(aa, cb, axis=2), bb
        if cb == 1:
            return aa, np.repeat(bb, ca, axis=2)
        raise ValueError(f"Channel mismatch: {ca} vs {cb}")

    def _bin(self, other: Any, fn) -> "ShaderValue":
        o = self._coerce(other)
        a, b = ShaderValue._align(self, o)
        return ShaderValue(fn(a, b), self.h, self.w)

    def _cmp(self, other: Any, fn) -> "ShaderValue":
        o = self._coerce(other)
        a, b = ShaderValue._align(self, o)
        return ShaderValue(fn(a, b).astype(np.float32), self.h, self.w)

    def __add__(self, other: Any) -> "ShaderValue":
        return self._bin(other, lambda a, b: a + b)

    def __radd__(self, other: Any) -> "ShaderValue":
        return self._coerce(other).__add__(self)

    def __sub__(self, other: Any) -> "ShaderValue":
        return self._bin(other, lambda a, b: a - b)

    def __rsub__(self, other: Any) -> "ShaderValue":
        return self._coerce(other).__sub__(self)

    def __mul__(self, other: Any) -> "ShaderValue":
        return self._bin(other, lambda a, b: a * b)

    def __rmul__(self, other: Any) -> "ShaderValue":
        return self._coerce(other).__mul__(self)

    def __truediv__(self, other: Any) -> "ShaderValue":
        return self._bin(other, lambda a, b: a / np.maximum(np.abs(b), 1e-8))

    def __rtruediv__(self, other: Any) -> "ShaderValue":
        return self._coerce(other).__truediv__(self)

    def __pow__(self, other: Any) -> "ShaderValue":
        return self._bin(other, lambda a, b: np.power(np.maximum(a, 0.0), b))

    def __rpow__(self, other: Any) -> "ShaderValue":
        return self._coerce(other).__pow__(self)

    def __neg__(self) -> "ShaderValue":
        return ShaderValue(-self.arr, self.h, self.w)

    def __gt__(self, other: Any) -> "ShaderValue":
        return self._cmp(other, np.greater)

    def __ge__(self, other: Any) -> "ShaderValue":
        return self._cmp(other, np.greater_equal)

    def __lt__(self, other: Any) -> "ShaderValue":
        return self._cmp(other, np.less)

    def __le__(self, other: Any) -> "ShaderValue":
        return self._cmp(other, np.less_equal)

    def __eq__(self, other: Any) -> "ShaderValue":
        return self._cmp(other, np.equal)

    def __ne__(self, other: Any) -> "ShaderValue":
        return self._cmp(other, np.not_equal)

    def _channel(self, idx: int) -> np.ndarray:
        if idx < self.channels:
            return self.arr[..., idx : idx + 1]
        if idx == 3:
            return np.ones((self.h, self.w, 1), dtype=np.float32)
        return self.arr[..., :1]

    def __getattr__(self, name: str) -> "ShaderValue":
        if name and all(ch in _SWIZZLE for ch in name):
            chans = [self._channel(_SWIZZLE[ch]) for ch in name]
            return ShaderValue(np.concatenate(chans, axis=2), self.h, self.w)
        raise AttributeError(name)

    def expanded(self, channels: int) -> "ShaderValue":
        target = int(max(1, channels))
        if self.channels == target:
            return self
        if self.channels == 1:
            return ShaderValue(np.repeat(self.arr, target, axis=2), self.h, self.w)
        if self.channels < target:
            pad = target - self.channels
            filler = np.ones((self.h, self.w, pad), dtype=np.float32)
            return ShaderValue(np.concatenate([self.arr, filler], axis=2), self.h, self.w)
        return ShaderValue(self.arr[..., :target], self.h, self.w)

    def set_swizzle(self, swizzle: str, value: Any) -> "ShaderValue":
        if not swizzle or any(ch not in _SWIZZLE for ch in swizzle):
            raise ValueError(f"Invalid swizzle '{swizzle}'")
        indices = [_SWIZZLE[ch] for ch in swizzle]
        target_channels = max(self.channels, max(indices) + 1)
        base = self.expanded(target_channels).arr.copy()
        val = self._coerce(value).arr

        if val.shape[2] == 1 and len(indices) > 1:
            parts = [val[..., :1] for _ in indices]
        else:
            parts = []
            for i in range(len(indices)):
                src_i = min(i, val.shape[2] - 1)
                parts.append(val[..., src_i : src_i + 1])
        for idx, part in zip(indices, parts):
            base[..., idx : idx + 1] = part
        return ShaderValue(base, self.h, self.w)


class ShaderTexture:
    def __init__(self, rgba: np.ndarray):
        if rgba.ndim != 3 or rgba.shape[2] not in (3, 4):
            raise ValueError(f"ShaderTexture expects [H,W,3|4], got {rgba.shape}")
        self.h = int(rgba.shape[0])
        self.w = int(rgba.shape[1])
        if rgba.shape[2] == 4:
            self.rgba = rgba.astype(np.float32, copy=False)
        else:
            alpha = np.ones((self.h, self.w, 1), dtype=np.float32)
            self.rgba = np.concatenate([rgba.astype(np.float32, copy=False), alpha], axis=2)

    def sample(self, uv: ShaderValue) -> ShaderValue:
        uv2 = uv.expanded(2).arr
        u = _clamp01(uv2[..., 0]) * float(self.w - 1)
        v = _clamp01(uv2[..., 1]) * float(self.h - 1)
        x0 = np.floor(u).astype(np.int32)
        y0 = np.floor(v).astype(np.int32)
        x1 = np.clip(x0 + 1, 0, self.w - 1)
        y1 = np.clip(y0 + 1, 0, self.h - 1)

        fx = (u - x0)[..., None]
        fy = (v - y0)[..., None]

        c00 = self.rgba[y0, x0]
        c10 = self.rgba[y0, x1]
        c01 = self.rgba[y1, x0]
        c11 = self.rgba[y1, x1]

        top = c00 * (1.0 - fx) + c10 * fx
        bot = c01 * (1.0 - fx) + c11 * fx
        out = top * (1.0 - fy) + bot * fy
        return ShaderValue(out.astype(np.float32, copy=False), self.h, self.w)


def _as_value(x: Any, h: int, w: int) -> ShaderValue:
    return x if isinstance(x, ShaderValue) else ShaderValue(x, h, w)


def _vecn(n: int, h: int, w: int, *args: Any) -> ShaderValue:
    target = int(max(1, n))
    if not args:
        return ShaderValue(0.0, h, w).expanded(target)

    parts: List[np.ndarray] = []
    for arg in args:
        v = _as_value(arg, h, w)
        for idx in range(v.channels):
            parts.append(v.arr[..., idx : idx + 1])

    if len(parts) == 1:
        arr = np.repeat(parts[0], target, axis=2)
        return ShaderValue(arr, h, w)

    while len(parts) < target:
        parts.append(parts[-1])
    return ShaderValue(np.concatenate(parts[:target], axis=2), h, w)


def _shader_env(tex: ShaderTexture, time_value: float) -> Dict[str, Any]:
    h, w = tex.h, tex.w
    uv_arr, frag_arr = _uv_frag_grid(h, w)
    uv = ShaderValue(uv_arr, h, w)
    frag = ShaderValue(frag_arr, h, w)
    resolution = ShaderValue([float(w), float(h)], h, w)

    def _unary(fn):
        return lambda x: ShaderValue(fn(_as_value(x, h, w).arr), h, w)

    def _binary(fn):
        return lambda a, b: ShaderValue(
            fn(*ShaderValue._align(_as_value(a, h, w), _as_value(b, h, w))),
            h,
            w,
        )

    def _pow_fn(a, b):
        aa, bb = ShaderValue._align(_as_value(a, h, w), _as_value(b, h, w))
        return ShaderValue(np.power(np.maximum(aa, 0.0), bb), h, w)

    def _clamp_fn(x, mn, mx):
        xx = _as_value(x, h, w)
        lo = _as_value(mn, h, w)
        hi = _as_value(mx, h, w)
        a, b = ShaderValue._align(xx, lo)
        a, c = ShaderValue._align(ShaderValue(a, h, w), hi)
        return ShaderValue(np.minimum(np.maximum(a, b), c), h, w)

    def _mix_fn(a, b, t):
        aa = _as_value(a, h, w)
        bb = _as_value(b, h, w)
        tt = _as_value(t, h, w)
        x, y = ShaderValue._align(aa, bb)
        t_arr = tt.arr if tt.channels != 1 else np.repeat(tt.arr, x.shape[2], axis=2)
        if t_arr.shape[2] != x.shape[2]:
            if t_arr.shape[2] == 1:
                t_arr = np.repeat(t_arr, x.shape[2], axis=2)
            else:
                raise ValueError("mix() channel mismatch")
        return ShaderValue(x * (1.0 - t_arr) + y * t_arr, h, w)

    def _step_fn(edge, x):
        ee, xx = ShaderValue._align(_as_value(edge, h, w), _as_value(x, h, w))
        return ShaderValue((xx >= ee).astype(np.float32), h, w)

    def _smoothstep_fn(edge0, edge1, x):
        e0 = _as_value(edge0, h, w)
        e1 = _as_value(edge1, h, w)
        xx = _as_value(x, h, w)
        a, b = ShaderValue._align(e0, e1)
        x_arr, a_arr = ShaderValue._align(xx, ShaderValue(a, h, w))
        x_arr, b_arr = ShaderValue._align(ShaderValue(x_arr, h, w), ShaderValue(b, h, w))
        denom = b_arr - a_arr
        denom = np.where(np.abs(denom) < 1e-6, np.where(denom < 0.0, -1e-6, 1e-6), denom)
        t = np.clip((x_arr - a_arr) / denom, 0.0, 1.0)
        return ShaderValue(t * t * (3.0 - 2.0 * t), h, w)

    def _dot_fn(a, b):
        aa, bb = ShaderValue._align(_as_value(a, h, w), _as_value(b, h, w))
        return ShaderValue(np.sum(aa * bb, axis=2, keepdims=True), h, w)

    def _length_fn(a):
        aa = _as_value(a, h, w).arr
        return ShaderValue(np.sqrt(np.maximum(np.sum(aa * aa, axis=2, keepdims=True), 0.0)), h, w)

    def _normalize_fn(a):
        aa = _as_value(a, h, w).arr
        l = np.sqrt(np.maximum(np.sum(aa * aa, axis=2, keepdims=True), 1e-8))
        return ShaderValue(aa / l, h, w)

    def _fract_fn(a):
        aa = _as_value(a, h, w).arr
        return ShaderValue(aa - np.floor(aa), h, w)

    def _mod_fn(a, b):
        aa, bb = ShaderValue._align(_as_value(a, h, w), _as_value(b, h, w))
        return ShaderValue(aa - bb * np.floor(aa / np.maximum(np.abs(bb), 1e-6)), h, w)

    def _where_fn(cond, a, b):
        cc = _as_value(cond, h, w).arr
        aa = _as_value(a, h, w)
        bb = _as_value(b, h, w)
        x, y = ShaderValue._align(aa, bb)
        mask = cc[..., :1] > 0.5
        if mask.shape[2] != x.shape[2]:
            mask = np.repeat(mask, x.shape[2], axis=2)
        return ShaderValue(np.where(mask, x, y), h, w)

    def _sample_fn(texture_like, uv_like):
        if not isinstance(texture_like, ShaderTexture):
            raise TypeError("texture() first argument must be a texture")
        return texture_like.sample(_as_value(uv_like, h, w))

    env: Dict[str, Any] = {
        "vec2": lambda *args: _vecn(2, h, w, *args),
        "vec3": lambda *args: _vecn(3, h, w, *args),
        "vec4": lambda *args: _vecn(4, h, w, *args),
        "float2": lambda *args: _vecn(2, h, w, *args),
        "float3": lambda *args: _vecn(3, h, w, *args),
        "float4": lambda *args: _vecn(4, h, w, *args),
        "sin": _unary(np.sin),
        "cos": _unary(np.cos),
        "tan": _unary(np.tan),
        "abs": _unary(np.abs),
        "sqrt": _unary(lambda x: np.sqrt(np.maximum(x, 0.0))),
        "exp": _unary(np.exp),
        "log": _unary(lambda x: np.log(np.maximum(x, 1e-8))),
        "floor": _unary(np.floor),
        "ceil": _unary(np.ceil),
        "pow": _pow_fn,
        "min": _binary(np.minimum),
        "max": _binary(np.maximum),
        "clamp": _clamp_fn,
        "clamp01": lambda x: _clamp_fn(x, 0.0, 1.0),
        "mix": _mix_fn,
        "lerp": _mix_fn,
        "step": _step_fn,
        "smoothstep": _smoothstep_fn,
        "dot": _dot_fn,
        "length": _length_fn,
        "normalize": _normalize_fn,
        "fract": _fract_fn,
        "mod": _mod_fn,
        "where": _where_fn,
        "texture": _sample_fn,
        "tex2D": _sample_fn,
        "sample": _sample_fn,
        "srcTex": tex,
        "inputTex": tex,
        "tex0": tex,
        "uv": uv,
        "fragCoord": frag,
        "resolution": resolution,
        "iResolution": resolution,
        "time": ShaderValue(float(time_value), h, w),
        "iTime": ShaderValue(float(time_value), h, w),
        "PI": math.pi,
        "pi": math.pi,
    }
    env["src"] = _sample_fn(tex, uv)
    env["color"] = env["src"]
    return env


def _eval_shader_expression(expr: str, env: Dict[str, Any]) -> ShaderValue:
    result = eval(expr, {"__builtins__": {}}, env)
    if isinstance(result, ShaderValue):
        return result
    if isinstance(result, (int, float, np.ndarray, list, tuple)):
        uv = env["uv"]
        return _as_value(result, uv.h, uv.w)
    raise TypeError(f"Unsupported shader result type: {type(result)}")


def _execute_shader(rgba: np.ndarray, statements: Sequence[Tuple[str, str, str, str]], time_value: float) -> np.ndarray:
    tex = ShaderTexture(rgba)
    env = _shader_env(tex, time_value=time_value)

    output: Optional[ShaderValue] = None
    for kind, lhs, op, rhs in statements:
        if kind == "return":
            output = _eval_shader_expression(rhs, env)
            break
        if kind == "expr":
            _eval_shader_expression(rhs, env)
            continue
        if kind != "assign":
            continue

        if "." in lhs:
            var_name, swizzle = lhs.split(".", 1)
        else:
            var_name, swizzle = lhs, ""

        current = env.get(var_name, ShaderValue(0.0, tex.h, tex.w))
        if not isinstance(current, ShaderValue):
            if isinstance(current, ShaderTexture):
                raise ValueError(f"Cannot assign to texture variable '{var_name}'")
            current = ShaderValue(current, tex.h, tex.w)

        rhs_value = _eval_shader_expression(rhs, env)
        if swizzle:
            base_part = getattr(current, swizzle)
            if op == "=":
                merged = current.set_swizzle(swizzle, rhs_value)
            elif op == "+=":
                merged = current.set_swizzle(swizzle, base_part + rhs_value)
            elif op == "-=":
                merged = current.set_swizzle(swizzle, base_part - rhs_value)
            elif op == "*=":
                merged = current.set_swizzle(swizzle, base_part * rhs_value)
            elif op == "/=":
                merged = current.set_swizzle(swizzle, base_part / rhs_value)
            else:
                raise ValueError(f"Unsupported assignment operator '{op}'")
            env[var_name] = merged
            continue

        if op == "=":
            env[var_name] = rhs_value
        elif op == "+=":
            env[var_name] = current + rhs_value
        elif op == "-=":
            env[var_name] = current - rhs_value
        elif op == "*=":
            env[var_name] = current * rhs_value
        elif op == "/=":
            env[var_name] = current / rhs_value
        else:
            raise ValueError(f"Unsupported assignment operator '{op}'")

    if output is None:
        if isinstance(env.get("color"), ShaderValue):
            output = env["color"]
        else:
            output = env["src"]

    out_rgba = output.expanded(4).arr
    return _clamp01(out_rgba.astype(np.float32, copy=False))


class xShader:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "shader_language": (["GLSL", "HLSL"], {"default": "GLSL"}),
                "shader_code": ("STRING", {"default": _DEFAULT_SHADER, "multiline": True}),
                "time": ("FLOAT", {"default": 0.0, "min": -100000.0, "max": 100000.0, "step": 0.01}),
                "time_mode": (["constant", "per_frame"], {"default": "constant"}),
                "time_step": ("FLOAT", {"default": 0.0416667, "min": -1000.0, "max": 1000.0, "step": 0.0001}),
                "strength": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 2.0, "step": 0.01}),
                "video_fps": ("INT", {"default": 24, "min": 1, "max": 240, "step": 1}),
            },
            "optional": {
                "fallback_on_error": ("BOOLEAN", {"default": True}),
            },
        }

    RETURN_TYPES = ("IMAGE", "STRING", "MKR_VIDEO")
    RETURN_NAMES = ("image", "shader_info", "video")
    FUNCTION = "run"
    CATEGORY = UTILITY_SHADER

    def run(
        self,
        image: torch.Tensor,
        shader_language: str = "GLSL",
        shader_code: str = _DEFAULT_SHADER,
        time: float = 0.0,
        time_mode: str = "constant",
        time_step: float = 0.0416667,
        strength: float = 1.0,
        video_fps: int = 24,
        fallback_on_error: bool = True,
    ):
        batch = _to_image_batch(image)
        source = batch.detach().cpu().numpy().astype(np.float32, copy=False)
        b, h, w, c = source.shape

        try:
            statements = _parse_shader_statements(shader_code)
            if not statements:
                passthrough_video = {
                    "kind": "video",
                    "frames": batch,
                    "fps": int(max(1, int(video_fps))),
                    "frame_count": int(b),
                    "width": int(w),
                    "height": int(h),
                    "duration": float(b / float(max(1, int(video_fps)))),
                    "has_audio": False,
                }
                return (image, "xShader: No executable shader statements found. Output is passthrough.", passthrough_video)
        except Exception as exc:
            passthrough_video = {
                "kind": "video",
                "frames": batch,
                "fps": int(max(1, int(video_fps))),
                "frame_count": int(b),
                "width": int(w),
                "height": int(h),
                "duration": float(b / float(max(1, int(video_fps)))),
                "has_audio": False,
            }
            return (image, f"xShader: Shader parse error: {exc}", passthrough_video)

        blend = float(max(0.0, min(2.0, strength)))
        mode = str(time_mode or "constant").strip().lower()
        if mode not in {"constant", "per_frame"}:
            mode = "constant"
        step = float(time_step)
        fps = int(max(1, int(video_fps)))

        out = np.empty_like(source, dtype=np.float32)
        errors: List[str] = []

        for idx in range(int(b)):
            sample = source[idx]
            rgb = sample[..., :3]
            alpha = sample[..., 3:4] if c == 4 else np.ones((h, w, 1), dtype=np.float32)
            rgba = np.concatenate([rgb, alpha], axis=2)
            frame_time = float(time + idx * step) if mode == "per_frame" else float(time)
            try:
                shaded = _execute_shader(rgba=rgba, statements=statements, time_value=frame_time)
            except Exception as exc:
                errors.append(f"[{idx}] {exc}")
                if fallback_on_error:
                    out[idx] = sample
                    continue
                passthrough_video = {
                    "kind": "video",
                    "frames": batch,
                    "fps": fps,
                    "frame_count": int(b),
                    "width": int(w),
                    "height": int(h),
                    "duration": float(b / float(fps)),
                    "has_audio": False,
                }
                return (image, f"xShader: Runtime error on sample {idx}: {exc}", passthrough_video)

            if blend <= 1.0:
                mixed = rgba * (1.0 - blend) + shaded * blend
            else:
                boost = blend - 1.0
                mixed = shaded + (shaded - rgba) * boost
            mixed = _clamp01(mixed)

            if c == 4:
                out[idx] = mixed
            else:
                out[idx] = mixed[..., :3]

        out_tensor = torch.from_numpy(out).to(device=batch.device, dtype=batch.dtype)
        video_payload = {
            "kind": "video",
            "frames": out_tensor.clamp(0.0, 1.0),
            "fps": fps,
            "frame_count": int(b),
            "width": int(w),
            "height": int(h),
            "duration": float(b / float(fps)),
            "has_audio": False,
        }

        msg = (
            f"xShader: Applied {shader_language.upper()}-style shader"
            f" ({len(statements)} statements, batch={b}, strength={blend:.2f}, "
            f"time={float(time):.2f}, mode={mode}, step={step:.4f}, fps={fps})"
        )
        if errors:
            msg += f" | errors={len(errors)} (fallback={'on' if fallback_on_error else 'off'}): {errors[0]}"
        return (out_tensor.clamp(0.0, 1.0), msg, video_payload)
