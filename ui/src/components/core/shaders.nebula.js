/* Dense energy haze filling the vortex. Brighter, tighter spiral pattern
   than the original — this is glowing energy, not interstellar gas. */

export const nebulaVert = /* glsl */ `
  varying vec2 vUv;
  void main() {
    vUv = uv;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`

export const nebulaFrag = /* glsl */ `
  uniform float uTime;
  uniform float uHaze;
  uniform float uBright;
  uniform float uCyan;
  uniform float uPurple;
  uniform float uAmp;

  varying vec2 vUv;

  float hash(vec2 p) {
    return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
  }

  float noise(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    vec2 u = f * f * (3.0 - 2.0 * f);
    return mix(
      mix(hash(i), hash(i + vec2(1.0, 0.0)), u.x),
      mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), u.x),
      u.y
    );
  }

  float fbm(vec2 p) {
    float v = 0.0;
    float a = 0.5;
    for (int i = 0; i < 5; i++) {
      v += a * noise(p);
      p *= 2.04;
      a *= 0.5;
    }
    return v;
  }

  void main() {
    vec2 uv = (vUv - 0.5) * 2.0;
    float r = length(uv);
    if (r > 1.0) discard;

    float ang = atan(uv.y, uv.x);

    // Tight logarithmic spiral — much more wound than a galaxy
    float phase = 3.0 * (ang - 5.5 * log(r + 0.12) - uTime * 0.09);
    float spiral = pow(0.5 + 0.5 * sin(phase), 1.6);

    // Secondary arm for depth
    float phase2 = 3.0 * (ang - 5.5 * log(r + 0.12) - uTime * 0.09 + 2.094);
    float spiral2 = pow(0.5 + 0.5 * sin(phase2), 1.8) * 0.6;

    // Third arm
    float phase3 = 3.0 * (ang - 5.5 * log(r + 0.12) - uTime * 0.09 + 4.189);
    float spiral3 = pow(0.5 + 0.5 * sin(phase3), 2.0) * 0.35;

    spiral *= smoothstep(0.08, 0.32, r);
    spiral2 *= smoothstep(0.1, 0.38, r);
    spiral3 *= smoothstep(0.12, 0.42, r);

    float tex = fbm(uv * 4.0 + vec2(uTime * 0.06, -uTime * 0.04));
    float dens = (spiral + spiral2 + spiral3) * (0.5 + 0.7 * tex);

    // Softer, fainter core — the orb does the bright work now
    dens += 0.18 * exp(-r * 6.0);
    dens += 0.09 * exp(-r * 3.5);

    dens *= smoothstep(1.0, 0.1, r);
    dens *= 0.6 + 0.4 * exp(-r * 1.0);

    // Colour ramp: white-hot center → cyan → blue → purple edges
    vec3 white = vec3(0.95, 0.98, 1.0);
    vec3 cyan = vec3(0.35, 0.82, 1.0);
    vec3 blue = vec3(0.15, 0.42, 1.0);
    vec3 purple = vec3(0.55, 0.25, 1.0);
    
    vec3 col = mix(white, cyan, smoothstep(0.0, 0.2, r));
    col = mix(col, blue, smoothstep(0.2, 0.5, r));
    col = mix(col, purple, smoothstep(0.55, 0.95, r));
    
    col = mix(col, vec3(0.25, 0.92, 1.0), uCyan * 0.5);
    col = mix(col, vec3(0.45, 0.26, 1.0), uPurple * 0.5);

    float a = dens * uHaze * 0.07 * (1.0 + uAmp * 0.2);
    gl_FragColor = vec4(col * uBright * (0.35 + dens * 0.8), a);
  }
`
