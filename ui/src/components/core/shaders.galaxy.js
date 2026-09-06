/* Tight energy-vortex spiral. NOT a spread-out galaxy — this is a concentrated,
   bright, swirling energy field matching the F.R.I.D.A.Y. reference image.
   Everything stays within ~4 world units and is much brighter than astronomy. */

export const vortexVert = /* glsl */ `
  uniform float uTime;
  uniform float uSpin;
  uniform float uShear;
  uniform float uSize;
  uniform float uScale;
  uniform float uAmp;
  uniform float uContract;
  uniform float uCyan;
  uniform float uPurple;
  uniform float uBright;

  attribute float aSize;
  attribute float aSeed;
  attribute float aRadius;
  attribute vec3 aColor;

  varying vec3 vColor;
  varying float vGlow;

  void main() {
    float r = aRadius;

    // Tight differential rotation: inner spins faster than outer
    float shear = uShear * 0.55 * sin(uTime * 0.4 + r * 0.3) * (1.6 / (r + 0.4));
    float ang = uTime * uSpin * (1.8 / (r + 0.3)) + shear;

    float c = cos(ang);
    float s = sin(ang);
    vec3 p = vec3(
      position.x * c - position.z * s,
      position.y,
      position.x * s + position.z * c
    );

    float swell = 1.0 + uAmp * 0.18 * (0.3 + r * 0.25);
    float pull = 1.0 - uContract * 0.25 * smoothstep(0.2, 3.0, r);
    p.xz *= swell * pull;
    p.y += sin(uTime * 1.3 + aSeed * 37.0) * 0.015 * (0.4 + r * 0.4);

    vec4 mv = modelViewMatrix * vec4(p, 1.0);
    gl_Position = projectionMatrix * mv;

    float tw = 0.55 + 0.45 * sin(uTime * (1.4 + aSeed * 4.0) + aSeed * 51.0);

    const float PT = 0.052;
    gl_PointSize = clamp(
      aSize * uSize * tw * PT * uScale / max(0.35, -mv.z),
      1.2,
      28.0
    );

    vec3 col = aColor;
    col = mix(col, vec3(0.28, 0.94, 1.0) * (0.5 + 0.5 * length(col)), uCyan * 0.6);
    col = mix(col, vec3(0.50, 0.30, 1.0) * (0.55 + 0.45 * length(col)), uPurple * 0.65);

    vColor = col * uBright;
    vGlow = tw;
  }
`

export const vortexFrag = /* glsl */ `
  varying vec3 vColor;
  varying float vGlow;

  void main() {
    vec2 d = gl_PointCoord - 0.5;
    float dist = dot(d, d) * 4.0;
    if (dist > 1.0) discard;
    float soft = 1.0 - dist;
    // Brighter core, softer halo — energy particles, not stars
    float a = pow(soft, 1.8);
    float core = exp(-dist * 10.0) * 0.6;
    gl_FragColor = vec4(vColor * (1.0 + 2.2 * a + core * 2.0), a * vGlow);
  }
`
